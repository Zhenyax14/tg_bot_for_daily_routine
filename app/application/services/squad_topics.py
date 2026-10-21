"""Servicio de aplicacion: memoria de las conversaciones ("temas") del topic
multi-bot.

Un tema es una cadena de respuestas: un mensaje que responde a otro ya
conocido entra en el tema de ese otro; cualquier otro mensaje abre un tema
nuevo. Por cada tema se guarda la transcripcion (lo que ven los bots como
contexto) y cuantos mensajes ha publicado cada bot, para el limite por tema.

Todo vive en memoria, indexado por message_id (el topic esta en un unico
chat): se pierde al reiniciar, y entonces el siguiente mensaje abre un tema
nuevo con el contador a cero.
"""
from __future__ import annotations

from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from itertools import count
from typing import Iterable

from domain.value_objects.squad_message import SquadMessage


@dataclass
class _Topic:
    messages: list[SquadMessage] = field(default_factory=list)
    sent: Counter = field(default_factory=Counter)


class SquadTopics:
    def __init__(self, max_topics: int = 300, max_messages: int = 40) -> None:
        self._max_topics = max_topics
        self._max_messages = max_messages
        self._topics: OrderedDict[int, _Topic] = OrderedDict()
        self._topic_of: dict[int, int] = {}
        self._ids = count(1)

    def knows(self, message_id: int) -> bool:
        return message_id in self._topic_of

    def record(self, message: SquadMessage, aliases: Iterable[int] = ()) -> int:
        """Guarda el mensaje (idempotente) y devuelve el id de su tema.
        `aliases`: otros ids que lo componen (respuesta troceada)."""
        topic_id = self._topic_of.get(message.message_id)
        if topic_id is None:
            topic_id = self._topic_of.get(message.reply_to) if message.reply_to is not None else None
            if topic_id is None:
                topic_id = self._open()
            topic = self._topics[topic_id]
            topic.messages.append(message)
            del topic.messages[:-self._max_messages]
        self._topics.move_to_end(topic_id)
        for message_id in (message.message_id, *aliases):
            self._topic_of[message_id] = topic_id
        return topic_id

    def transcript(self, topic_id: int, until_message_id: int) -> list[SquadMessage]:
        """Mensajes del tema hasta `until_message_id` incluido: lo que se
        publique despues mientras el bot piensa no forma parte de su contexto."""
        topic = self._topics.get(topic_id)
        messages = topic.messages if topic is not None else []
        for index, message in enumerate(messages):
            if message.message_id == until_message_id:
                return messages[:index + 1]
        return list(messages)

    def latest(self) -> list[SquadMessage]:
        """Mensajes del tema con actividad mas reciente (vacio si no hay ninguno)."""
        if not self._topics:
            return []
        return list(next(reversed(self._topics.values())).messages)

    def try_reserve(self, topic_id: int, slot: int, limit: int) -> int | None:
        """Reserva un mensaje del bot en el tema. Devuelve su numero (1..limit)
        o None si ya agoto el limite."""
        topic = self._topics.get(topic_id)
        if topic is None:
            return None
        sent = topic.sent
        if sent[slot] >= limit:
            return None
        sent[slot] += 1
        return sent[slot]

    def reset_counts(self, topic_id: int) -> None:
        """Pone a cero los mensajes de todos los bots en el tema (ha
        intervenido una persona: ya no es un bucle entre bots)."""
        topic = self._topics.get(topic_id)
        if topic is not None:
            topic.sent.clear()

    def release(self, topic_id: int, slot: int) -> None:
        """Devuelve una reserva cuyo mensaje no llego a publicarse."""
        topic = self._topics.get(topic_id)
        if topic is not None and topic.sent[slot] > 0:
            topic.sent[slot] -= 1

    def _open(self) -> int:
        topic_id = next(self._ids)
        self._topics[topic_id] = _Topic()
        while len(self._topics) > self._max_topics:
            old_id, _ = self._topics.popitem(last=False)
            for message_id in [m for m, t in self._topic_of.items() if t == old_id]:
                del self._topic_of[message_id]
        return topic_id
