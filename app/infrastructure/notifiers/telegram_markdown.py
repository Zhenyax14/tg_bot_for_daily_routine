"""Notifier que recibe Markdown (lo que escriben los modelos) y lo publica en
un hilo como HTML de Telegram, troceado si es largo. Si Telegram rechaza el
HTML convertido, ese trozo se reenvia como texto plano (mismo criterio que el
asistente y el topic multi-bot).

Se usa para publicar con la cuenta de un bot del topic (su propio token) en
otro hilo del grupo, p. ej. el analisis de mercado en el hilo de alertas.

A diferencia de TelegramNotifier, si Telegram falla el error se registra y se
RELANZA: quien publica decide que hacer (el analisis de mercado lo registra
como no publicado).
"""
from __future__ import annotations

import logging

from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import BadRequest, TelegramError

from infrastructure.telegram.markdown_to_html import markdown_to_telegram_html, split_markdown

logger = logging.getLogger(__name__)

_CHUNK_CHARS = 3500


class TelegramMarkdownNotifier:
    def __init__(self, token: str, chat_id: str | int, thread_id: int | None = None) -> None:
        self._bot = Bot(token=token)
        self._chat_id = chat_id
        self._thread_id = thread_id

    async def send(self, text: str) -> None:
        try:
            for chunk in split_markdown(text, _CHUNK_CHARS):
                await self._send_chunk(chunk)
        except TelegramError as exc:
            logger.error("Fallo al publicar Markdown en el hilo %s: %s", self._thread_id, exc)
            raise

    async def _send_chunk(self, markdown: str) -> None:
        try:
            await self._bot.send_message(
                self._chat_id, markdown_to_telegram_html(markdown),
                parse_mode=ParseMode.HTML, message_thread_id=self._thread_id,
            )
        except BadRequest as exc:
            logger.warning("HTML rechazado por Telegram (%s), se envia como texto plano", exc)
            await self._bot.send_message(self._chat_id, markdown, message_thread_id=self._thread_id)
