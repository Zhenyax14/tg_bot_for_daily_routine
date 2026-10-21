"""Handler del topic multi-bot: uno por bot (slot), registrado en la
Application de ese bot.

Solo atiende el topic configurado (AI_BOTS_THREAD_ID) del grupo. Un mensaje
de una persona se pasa al caso de uso; si menciona a ESTE bot o responde a un
mensaje suyo, va dirigido a el. Cada bot recibe su propia copia del mensaje,
asi que una mencion a dos bots la atiende cada uno por su lado.

Solo texto (y el pie de las fotos): las imagenes no se envian al modelo.
"""
from __future__ import annotations

import logging

from telegram import Message, Update
from telegram.constants import MessageEntityType
from telegram.ext import ContextTypes

from application.use_cases.run_squad_conversation import RunSquadConversation
from domain.value_objects.squad_message import SquadMessage
from infrastructure.telegram.telegram_squad_gateway import TelegramSquadGateway

logger = logging.getLogger(__name__)


class SquadMessageHandler:
    def __init__(self, slot: int, conversation: RunSquadConversation, gateway: TelegramSquadGateway) -> None:
        self._slot = slot
        self._conversation = conversation
        self._gateway = gateway

    async def __call__(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        if message is None or message.from_user is None or message.from_user.is_bot:
            return
        if not (message.is_topic_message and message.message_thread_id == self._gateway.thread_id):
            return
        text = message.text or message.caption or ""
        if not text.strip():
            return

        quoted = _quoted(message)
        me = context.bot
        addressed = _mentions(message, me.username) or (
            quoted is not None and quoted.from_user is not None and quoted.from_user.id == me.id
        )
        self._conversation.on_message(
            SquadMessage(
                message.message_id, _author(message), text,
                reply_to=quoted.message_id if quoted else None,
            ),
            self._slot if addressed else None,
            self._as_squad_message(quoted) if quoted else None,
        )

    def _as_squad_message(self, message: Message) -> SquadMessage | None:
        text = message.text or message.caption or ""
        if not text:
            return None
        user_id = message.from_user.id if message.from_user else None
        slot = next((m.slot for m in self._gateway.members().values() if m.user_id == user_id), None)
        return SquadMessage(message.message_id, _author(message), text, bot_slot=slot)


def _quoted(message: Message) -> Message | None:
    """Mensaje al que responde. En un topic, todo mensaje "suelto" llega como
    reply al mensaje de creacion del topic: eso no cuenta como respuesta."""
    quoted = message.reply_to_message
    if quoted is None or quoted.message_id == message.message_thread_id or quoted.forum_topic_created:
        return None
    return quoted


def _author(message: Message) -> str:
    return message.from_user.full_name if message.from_user else "Участник"


def _mentions(message: Message, username: str) -> bool:
    target = f"@{username}".lower()
    found = {
        **message.parse_entities([MessageEntityType.MENTION]),
        **message.parse_caption_entities([MessageEntityType.MENTION]),
    }
    return any(text.lower() == target for text in found.values())
