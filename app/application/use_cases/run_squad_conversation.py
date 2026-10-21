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
"""
from __future__ import annotations

import asyncio
import logging
from typing import Coroutine, Mapping

from application.ports.language_model import LanguageModel, LanguageModelError
from application.ports.squad_gateway import SquadDeliveryError, SquadGateway
from application.services.squad_persona_service import SquadPersonaService
from application.services.squad_prompt import build_squad_instruction, mentioned_slots, squad_conversation
from application.services.squad_topics import SquadTopics
from domain.value_objects.squad_message import SquadMessage

logger = logging.getLogger(__name__)

MAX_MESSAGES_PER_BOT_PER_TOPIC = 5


class RunSquadConversation:
    def __init__(
        self,
        personas: SquadPersonaService,
        models: Mapping[int, LanguageModel],
        gateway: SquadGateway,
        topics: SquadTopics,
        limit: int = MAX_MESSAGES_PER_BOT_PER_TOPIC,
    ) -> None:
        self._personas = personas
        self._models = models
        self._gateway = gateway
        self._topics = topics
        self._limit = limit
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
        for other in mentioned_slots(answer, members, exclude=slot):
            self._spawn(self._respond(other, reply, topic_id, by_person=False))

    async def _report_failure(self, slot: int, reply_to: int) -> None:
        try:
            await self._gateway.report_failure(slot, reply_to)
        except SquadDeliveryError as exc:
            logger.error("Squad: tampoco se pudo avisar del fallo: %s", exc)
