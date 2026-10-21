"""Caso de uso: conversacion del topic multi-bot.

Una persona menciona a un bot (o responde a uno de sus mensajes) -> ese bot
contesta, como reply al mensaje que lo activo. Si en su respuesta menciona a
otro bot, ese otro contesta a su vez, y asi sucesivamente: Telegram nunca
entrega a un bot los mensajes de otro bot, asi que el relevo entre bots se
hace aqui dentro, no a traves de Telegram.

Freno anti-bucle: entre dos intervenciones de personas, cada bot publica
como maximo `limit` mensajes por tema (cadena de respuestas, ver
SquadTopics). Agotado el cupo, se calla; en cuanto una persona escribe en el
tema el cupo vuelve a empezar, asi que a una persona siempre se le contesta.

Cada respuesta corre en su propia tarea: una cadena entre bots puede durar
minutos y no debe bloquear el procesado de otros mensajes.

Mensajes espontaneos: cada SPONTANEOUS_CHECK_MINUTES el planificador llama a
`speak_up`, que tira un dado por bot segun su media de mensajes al dia; si a
alguno le toca, publica un mensaje suelto (nuevo tema) acorde a su rol y a la
ultima conversacion del topic. Si menciona a otro bot, el relevo sigue igual.
"""
from __future__ import annotations

import asyncio
import logging
import random
from typing import Callable, Coroutine, Mapping, Sequence

from application.ports.language_model import LanguageModel, LanguageModelError
from application.ports.squad_gateway import SquadDeliveryError, SquadGateway
from application.services.squad_persona_service import SquadPersonaService
from application.services.squad_prompt import (
    build_squad_instruction,
    mentioned_slots,
    spontaneous_conversation,
    squad_conversation,
)
from application.services.squad_topics import SquadTopics
from domain.value_objects.squad_message import SquadMember, SquadMessage

logger = logging.getLogger(__name__)

MAX_MESSAGES_PER_BOT_PER_TOPIC = 5
SPONTANEOUS_CHECK_MINUTES = 5
_MINUTES_PER_DAY = 24 * 60


class RunSquadConversation:
    def __init__(
        self,
        personas: SquadPersonaService,
        models: Mapping[int, LanguageModel],
        gateway: SquadGateway,
        topics: SquadTopics,
        limit: int = MAX_MESSAGES_PER_BOT_PER_TOPIC,
        roll: Callable[[], float] = random.random,
        pick: Callable[[Sequence[int]], int] = random.choice,
    ) -> None:
        self._personas = personas
        self._models = models
        self._gateway = gateway
        self._topics = topics
        self._limit = limit
        self._roll = roll
        self._pick = pick
        self._tasks: set[asyncio.Task] = set()

    def on_message(self, message: SquadMessage, addressed: int | None, quoted: SquadMessage | None = None) -> None:
        """Mensaje de una persona en el topic. `addressed`: slot del bot al
        que va dirigido (None = solo se guarda como contexto). `quoted`: el
        mensaje al que responde, por si no esta en memoria (tras reiniciar)."""
        if quoted is not None and not self._topics.knows(quoted.message_id):
            self._topics.record(quoted)
        is_new = not self._topics.knows(message.message_id)
        topic_id = self._topics.record(message)
        # Cada bot recibe su copia del mensaje: el cupo se reinicia solo con la
        # primera, para no anular la reserva de un bot que ya esta contestando.
        if is_new:
            self._topics.reset_counts(topic_id)
        if addressed is not None:
            self._spawn(self._respond(addressed, message, topic_id, by_person=True))

    async def speak_up(self) -> None:
        """Tick del planificador: como mucho un bot habla por iniciativa propia.
        Si hay una conversacion en curso no interrumpe."""
        if self._tasks:
            return
        members = self._gateway.members()
        candidates = []
        for slot in sorted(self._models):
            persona = self._personas.get(slot)
            chance = persona.spontaneous_per_day * SPONTANEOUS_CHECK_MINUTES / _MINUTES_PER_DAY
            if persona.enabled and slot in members and self._roll() < chance:
                candidates.append(slot)
        if candidates:
            await self._speak(self._pick(candidates))

    async def wait_idle(self) -> None:
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def close(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*list(self._tasks), return_exceptions=True)

    def _spawn(self, coroutine: Coroutine) -> None:
        task = asyncio.create_task(coroutine)
        self._tasks.add(task)
        task.add_done_callback(self._finished)

    def _finished(self, task: asyncio.Task) -> None:
        self._tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            logger.error("Squad: fallo inesperado", exc_info=task.exception())

    async def _respond(self, slot: int, trigger: SquadMessage, topic_id: int, by_person: bool) -> None:
        persona = self._personas.get(slot)
        members = self._gateway.members()
        model = self._models.get(slot)
        if not persona.enabled or slot not in members or model is None:
            logger.info("Squad: bot %s inactivo, no responde", slot)
            return
        number = self._topics.try_reserve(topic_id, slot, self._limit)
        if number is None:
            logger.info("Squad: bot %s agoto sus %d mensajes en el tema %s", slot, self._limit, topic_id)
            return

        me = members[slot]
        others = [member for other, member in sorted(members.items()) if other != slot]
        instruction = build_squad_instruction(persona, me, others, number, self._limit)
        conversation = squad_conversation(self._topics.transcript(topic_id, trigger.message_id), slot)
        try:
            await self._gateway.typing(slot)
            answer = await model.generate(persona.model, instruction, conversation)
            sent = await self._gateway.send(slot, answer, trigger.message_id)
        except (LanguageModelError, SquadDeliveryError) as exc:
            self._topics.release(topic_id, slot)
            logger.error("Squad: bot %s no pudo responder: %s", slot, exc)
            if by_person:
                await self._report_failure(slot, trigger.message_id)
            return

        logger.info("Squad: bot %s respondio en el tema %s (%d/%d)", slot, topic_id, number, self._limit)
        reply = SquadMessage(sent[-1], me.name, answer, bot_slot=slot, reply_to=trigger.message_id)
        self._topics.record(reply, aliases=sent[:-1])
        self._relay(reply, topic_id, members)

    async def _speak(self, slot: int) -> None:
        members = self._gateway.members()
        persona = self._personas.get(slot)
        me = members[slot]
        others = [member for other, member in sorted(members.items()) if other != slot]
        instruction = build_squad_instruction(persona, me, others, 1, self._limit)
        conversation = spontaneous_conversation(self._topics.latest(), slot)
        try:
            await self._gateway.typing(slot)
            text = await self._models[slot].generate(persona.model, instruction, conversation)
            sent = await self._gateway.send(slot, text, None)
        except (LanguageModelError, SquadDeliveryError) as exc:
            logger.error("Squad: bot %s no pudo hablar por iniciativa propia: %s", slot, exc)
            return

        message = SquadMessage(sent[-1], me.name, text, bot_slot=slot)
        topic_id = self._topics.record(message, aliases=sent[:-1])
        self._topics.try_reserve(topic_id, slot, self._limit)
        logger.info("Squad: bot %s hablo por iniciativa propia (tema %s)", slot, topic_id)
        self._relay(message, topic_id, members)

    def _relay(self, message: SquadMessage, topic_id: int, members: Mapping[int, SquadMember]) -> None:
        """Los bots mencionados en un mensaje de bot le contestan."""
        for other in mentioned_slots(message.text, members, exclude=message.bot_slot):
            self._spawn(self._respond(other, message, topic_id, by_person=False))

    async def _report_failure(self, slot: int, reply_to: int) -> None:
        try:
            await self._gateway.report_failure(slot, reply_to)
        except SquadDeliveryError as exc:
            logger.error("Squad: tampoco se pudo avisar del fallo: %s", exc)
