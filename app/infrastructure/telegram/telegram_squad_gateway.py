"""Adaptador de SquadGateway: publica en el topic multi-bot como cualquiera
de los bots conectados. Cada bot se registra al arrancar (register), con el
`Bot` ya inicializado para conocer su @username.

Textos visibles en Telegram -> ruso.
"""
from __future__ import annotations

import logging
from typing import Mapping

from telegram import Bot, Message, ReplyParameters
from telegram.constants import ChatAction, ParseMode
from telegram.error import BadRequest, TelegramError

from application.ports.squad_gateway import SquadDeliveryError
from domain.value_objects.squad_message import SquadMember
from infrastructure.telegram.markdown_to_html import markdown_to_telegram_html, split_markdown

logger = logging.getLogger(__name__)

_FAILURE_REPLY = "⚠️ Не удалось получить ответ. Попробуйте позже."
_CHUNK_CHARS = 3500  # mismo margen que el asistente del hilo General


class TelegramSquadGateway:
    def __init__(self, chat_id: int, thread_id: int) -> None:
        self._chat_id = chat_id
        self._thread_id = thread_id
        self._bots: dict[int, Bot] = {}
        self._members: dict[int, SquadMember] = {}

    @property
    def thread_id(self) -> int:
        return self._thread_id

    def register(self, slot: int, bot: Bot) -> SquadMember:
        member = SquadMember(slot, bot.id, bot.username, bot.first_name)
        self._bots[slot] = bot
        self._members[slot] = member
        return member

    def members(self) -> Mapping[int, SquadMember]:
        return dict(self._members)

    async def typing(self, slot: int) -> None:
        try:
            await self._bots[slot].send_chat_action(
                chat_id=self._chat_id, action=ChatAction.TYPING, message_thread_id=self._thread_id
            )
        except TelegramError as exc:
            logger.warning("Squad: typing de bot %s fallo: %s", slot, exc)

    async def send(self, slot: int, text: str, reply_to: int | None) -> tuple[int, ...]:
        sent = []
        try:
            for chunk in split_markdown(text, _CHUNK_CHARS):
                sent.append(await self._send_formatted(self._bots[slot], chunk, reply_to))
        except TelegramError as exc:
            raise SquadDeliveryError(f"Telegram: {exc}") from exc
        return tuple(message.message_id for message in sent)

    async def report_failure(self, slot: int, reply_to: int) -> None:
        try:
            await self._bots[slot].send_message(
                self._chat_id, _FAILURE_REPLY, message_thread_id=self._thread_id,
                reply_parameters=self._reply(reply_to),
            )
        except TelegramError as exc:
            raise SquadDeliveryError(f"Telegram: {exc}") from exc

    async def _send_formatted(self, bot: Bot, markdown: str, reply_to: int | None) -> Message:
        """Como en el asistente del hilo General: si Telegram no acepta el
        HTML convertido, se reenvia el trozo como texto plano."""
        try:
            return await bot.send_message(
                self._chat_id, markdown_to_telegram_html(markdown), parse_mode=ParseMode.HTML,
                message_thread_id=self._thread_id, reply_parameters=self._reply(reply_to),
            )
        except BadRequest as exc:
            logger.warning("Squad: HTML rechazado por Telegram (%s), se envia como texto plano", exc)
            return await bot.send_message(
                self._chat_id, markdown, message_thread_id=self._thread_id,
                reply_parameters=self._reply(reply_to),
            )

    @staticmethod
    def _reply(message_id: int | None) -> ReplyParameters | None:
        # Si el mensaje citado se borro mientras el bot pensaba, se publica igual.
        if message_id is None:
            return None
        return ReplyParameters(message_id, allow_sending_without_reply=True)
