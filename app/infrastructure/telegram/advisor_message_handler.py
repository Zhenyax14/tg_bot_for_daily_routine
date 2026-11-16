"""Handler del robo-advisor (el bot principal) en el hilo de alertas.

Registrado en la Application del bot principal, en un grupo de handlers
aparte del asistente del hilo General. Solo atiende el hilo de alertas (PRICE_ALERTS_THREAD_ID): un
mensaje de una persona que menciona al bot o responde a un mensaje suyo
(incluidos sus analisis automaticos) se contesta como reply.

Conversacion: al responder a un mensaje del bot se recupera el hilo de
ConversationMemory; si no esta (reinicio, o es un analisis automatico) se usa
el texto del mensaje citado como turno del propio bot. Una mencion que
responde a otra persona incluye su mensaje como texto citado.

Solo texto (y el pie de las fotos). Textos visibles en Telegram -> ruso.
"""
from __future__ import annotations

import logging
import re

from telegram import Message, ReplyParameters, Update
from telegram.constants import ChatAction, MessageEntityType, ParseMode
from telegram.error import BadRequest, TelegramError
from telegram.ext import ContextTypes

from application.ports.language_model import LanguageModelError
from application.services.conversation_memory import ConversationMemory
from application.services.market_analysis_prompt import question_turn
from application.use_cases.answer_advisor_question import AnswerAdvisorQuestion
from domain.value_objects.chat_turn import ChatTurn
from infrastructure.telegram.markdown_to_html import markdown_to_telegram_html, split_markdown

logger = logging.getLogger(__name__)

_ERROR_REPLY = "⚠️ Не удалось подготовить анализ. Попробуйте позже."
_EMPTY_PROMPT_REPLY = "Слушаю. Например: «сделай анализ рынка на сейчас»."
_CHUNK_CHARS = 3500


class AdvisorMessageHandler:
    def __init__(self, thread_id: int, answer: AnswerAdvisorQuestion, memory: ConversationMemory) -> None:
        self._thread_id = thread_id
        self._answer = answer
        self._memory = memory

    async def __call__(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        if message is None or message.from_user is None or message.from_user.is_bot:
            return
        if not (message.is_topic_message and message.message_thread_id == self._thread_id):
            return

        me = context.bot
        quoted = _quoted(message)
        replied_to_me = quoted is not None and quoted.from_user is not None and quoted.from_user.id == me.id
        if not (_mentions(message, me.username) or replied_to_me):
            return

        text = _strip_mention(message.text or message.caption or "", me.username)
        if not text:
            await _reply(message, _EMPTY_PROMPT_REPLY)
            return
        author = message.from_user.full_name

        history: list[ChatTurn] = []
        if replied_to_me:
            history = self._memory.history_for(quoted.chat_id, quoted.message_id) or (
                [ChatTurn("model", quoted.text or quoted.caption or "")] if (quoted.text or quoted.caption) else []
            )
        elif quoted is not None and (quoted.text or quoted.caption):
            quoted_author = quoted.from_user.full_name if quoted.from_user else "Участник"
            text = f"{text}\n\n[Quoted message from {quoted_author}]\n{quoted.text or quoted.caption}"
        question = question_turn(author, text)

        logger.info("Robo-advisor: pregunta de %s en el hilo de alertas", author)
        try:
            await context.bot.send_chat_action(
                message.chat_id, ChatAction.TYPING, message_thread_id=self._thread_id
            )
        except TelegramError:
            pass
        try:
            answer = await self._answer.execute(history, question)
        except LanguageModelError as exc:
            logger.error("Robo-advisor: el modelo no respondio: %s", exc)
            await _reply(message, _ERROR_REPLY)
            return
        lead = message
        try:
            for chunk in split_markdown(answer, _CHUNK_CHARS):
                lead = await _reply_formatted(lead, chunk)
        except TelegramError as exc:
            logger.error("Robo-advisor: no se pudo publicar la respuesta: %s", exc)
            return
        self._memory.remember(lead.chat_id, lead.message_id, [*history, question, ChatTurn("model", answer)])


def _quoted(message: Message) -> Message | None:
    """En un topic, todo mensaje "suelto" llega como reply al mensaje de
    creacion del topic: eso no cuenta como respuesta."""
    quoted = message.reply_to_message
    if quoted is None or quoted.message_id == message.message_thread_id or quoted.forum_topic_created:
        return None
    return quoted


def _mentions(message: Message, username: str) -> bool:
    target = f"@{username}".lower()
    found = {
        **message.parse_entities([MessageEntityType.MENTION]),
        **message.parse_caption_entities([MessageEntityType.MENTION]),
    }
    return any(text.lower() == target for text in found.values())


def _strip_mention(text: str, username: str) -> str:
    text = re.sub(rf"@{re.escape(username)}(?!\w)", "", text, flags=re.IGNORECASE)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


async def _reply(message: Message, text: str) -> None:
    try:
        await message.reply_text(text, reply_parameters=ReplyParameters(message.message_id, allow_sending_without_reply=True))
    except TelegramError as exc:
        logger.error("Robo-advisor: no se pudo responder: %s", exc)


async def _reply_formatted(message: Message, markdown: str) -> Message:
    """Si Telegram no acepta el HTML convertido, se reenvia como texto plano."""
    reply = ReplyParameters(message.message_id, allow_sending_without_reply=True)
    try:
        return await message.reply_text(
            markdown_to_telegram_html(markdown), parse_mode=ParseMode.HTML, reply_parameters=reply
        )
    except BadRequest as exc:
        logger.warning("Robo-advisor: HTML rechazado por Telegram (%s), se envia como texto plano", exc)
        return await message.reply_text(markdown, reply_parameters=reply)
