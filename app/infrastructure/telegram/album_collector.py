"""Agrupa los mensajes de un album de Telegram.

Telegram entrega un album (varias fotos enviadas juntas) como mensajes
sueltos que comparten `media_group_id`, y solo uno lleva el pie. Este
colector los acumula y, cuando dejan de llegar durante `delay` segundos,
entrega el grupo completo (ordenado) al callback.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from telegram import Message
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

AlbumCallback = Callable[[list[Message], ContextTypes.DEFAULT_TYPE], Awaitable[None]]


@dataclass
class _Pending:
    messages: list[Message] = field(default_factory=list)
    task: asyncio.Task | None = None


class AlbumCollector:
    def __init__(self, on_complete: AlbumCallback, delay: float = 2.0) -> None:
        self._on_complete = on_complete
        self._delay = delay
        self._pending: dict[tuple[int, str], _Pending] = {}

    def add(self, message: Message, context: ContextTypes.DEFAULT_TYPE) -> None:
        key = (message.chat_id, message.media_group_id)
        pending = self._pending.setdefault(key, _Pending())
        pending.messages.append(message)
        if pending.task is not None:
            pending.task.cancel()
        pending.task = asyncio.create_task(self._flush_later(key, context))

    async def _flush_later(self, key: tuple[int, str], context: ContextTypes.DEFAULT_TYPE) -> None:
        await asyncio.sleep(self._delay)
        pending = self._pending.pop(key)
        messages = sorted(pending.messages, key=lambda m: m.message_id)
        try:
            await self._on_complete(messages, context)
        except Exception:
            logger.exception("IA: fallo procesando el album %s", key[1])
