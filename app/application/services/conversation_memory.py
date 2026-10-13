"""Servicio de aplicacion: recuerda en memoria el hilo de conversacion que
llevo a cada respuesta del bot, indexado por el id del mensaje enviado. Asi,
cuando alguien responde a un mensaje del bot, se recupera todo el hilo y no
solo el ultimo mensaje (Telegram solo incluye un nivel de reply).

Los hilos incluyen las imagenes (para preguntas de seguimiento sobre un
grafico), asi que ademas del numero de hilos y turnos se acota el total de
bytes de imagen: se expulsan los hilos mas antiguos hasta quedar por debajo.
Se pierde al reiniciar (aceptable: el handler cae a usar el mensaje citado).
"""
from __future__ import annotations

from collections import OrderedDict
from typing import Sequence

from domain.value_objects.chat_turn import ChatTurn


class ConversationMemory:
    def __init__(
        self,
        max_threads: int = 500,
        max_turns: int = 20,
        max_image_bytes: int = 64 * 1024 * 1024,
    ) -> None:
        self._max_threads = max_threads
        self._max_turns = max_turns
        self._max_image_bytes = max_image_bytes
        self._threads: OrderedDict[tuple[int, int], tuple[ChatTurn, ...]] = OrderedDict()
        self._image_bytes = 0

    def history_for(self, chat_id: int, message_id: int) -> list[ChatTurn] | None:
        turns = self._threads.get((chat_id, message_id))
        return list(turns) if turns is not None else None

    def remember(self, chat_id: int, message_id: int, conversation: Sequence[ChatTurn]) -> None:
        turns = tuple(conversation)[-self._max_turns:]
        key = (chat_id, message_id)
        self._forget(key)
        self._threads[key] = turns
        self._image_bytes += _image_bytes(turns)
        # Cota conservadora: los hilos encadenados comparten los mismos
        # objetos de imagen, pero se cuentan en cada hilo que los contiene.
        while self._threads and (
            len(self._threads) > self._max_threads or self._image_bytes > self._max_image_bytes
        ):
            self._forget(next(iter(self._threads)))

    def _forget(self, key: tuple[int, int]) -> None:
        turns = self._threads.pop(key, None)
        if turns is not None:
            self._image_bytes -= _image_bytes(turns)


def _image_bytes(turns: tuple[ChatTurn, ...]) -> int:
    return sum(turn.image_bytes for turn in turns)
