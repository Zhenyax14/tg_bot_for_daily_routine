"""Servicio de aplicacion: recuerda en memoria el hilo de conversacion que
llevo a cada respuesta del bot, indexado por el id del mensaje enviado. Asi,
cuando alguien responde a un mensaje del bot, se recupera todo el hilo y no
solo el ultimo mensaje (Telegram solo incluye un nivel de reply).

Acotado en numero de hilos y de turnos; se pierde al reiniciar (aceptable:
el handler cae a usar solo el mensaje citado)."""
from __future__ import annotations

from collections import OrderedDict
from typing import Sequence

from domain.value_objects.chat_turn import ChatTurn


class ConversationMemory:
    def __init__(self, max_threads: int = 500, max_turns: int = 20) -> None:
        self._max_threads = max_threads
        self._max_turns = max_turns
        self._threads: OrderedDict[tuple[int, int], tuple[ChatTurn, ...]] = OrderedDict()

    def history_for(self, chat_id: int, message_id: int) -> list[ChatTurn] | None:
        turns = self._threads.get((chat_id, message_id))
        return list(turns) if turns is not None else None

    def remember(self, chat_id: int, message_id: int, conversation: Sequence[ChatTurn]) -> None:
        turns = tuple(conversation)[-self._max_turns:]
        key = (chat_id, message_id)
        self._threads[key] = turns
        self._threads.move_to_end(key)
        while len(self._threads) > self._max_threads:
            self._threads.popitem(last=False)
