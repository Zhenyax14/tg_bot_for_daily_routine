"""Handler de menciones: en el hilo General del grupo, un mensaje que menciona
al bot (@nombrebot) o que responde a un mensaje suyo se envia al modelo de
lenguaje y la respuesta se publica como reply.

Al responder a un mensaje del bot se envia la conversacion por turnos (lo que
dijo el bot como `model`, lo de las personas como `user`): si se le pasara su
propia respuesta como texto citado de un tercero, el modelo le contestaria a
ella y "hablaria consigo mismo".

Capa driving: traduce el Update a una llamada al caso de uso. Textos visibles
en Telegram -> ruso.
"""
from __future__ import annotations

import logging

from telegram import Message, Update
from telegram.constants import ChatAction, MessageEntityType, MessageLimit
from telegram.ext import ContextTypes

from application.ports.language_model import LanguageModelError
from application.services.conversation_memory import ConversationMemory
from application.use_cases.answer_mention import AnswerMention
from domain.value_objects.chat_turn import ChatTurn

logger = logging.getLogger(__name__)

_ERROR_REPLY = "⚠️ Не удалось получить ответ. Попробуйте позже."
_EMPTY_PROMPT_REPLY = "Слушаю 🙂 Напишите вопрос после упоминания."


class AiMentionHandler:
    def __init__(self, answer_mention: AnswerMention, memory: ConversationMemory) -> None:
        self._answer_mention = answer_mention
        self._memory = memory

    async def __call__(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        if message is None or not message.text or not self._answer_mention.enabled:
            return
        # Solo el hilo General: los mensajes dentro de un topic llevan is_topic_message.
        if message.is_topic_message:
            return

        bot_username = context.bot.username
        replied_to_bot = _is_reply_to(message, context.bot.id)
        if not (replied_to_bot or _mentions(message, bot_username)):
            return

        question = _strip_mention(message.text, bot_username)
        if not question:
            await message.reply_text(_EMPTY_PROMPT_REPLY)
            return

        conversation = self._conversation(message, question, replied_to_bot)
        await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)
        try:
            answer = await self._answer_mention.execute(conversation)
        except LanguageModelError as exc:
            logger.error("IA: %s", exc)
            await message.reply_text(_ERROR_REPLY)
            return

        thread = [*conversation, ChatTurn("model", answer)]
        for chunk in _split(answer, MessageLimit.MAX_TEXT_LENGTH):
            sent = await message.reply_text(chunk)
            self._memory.remember(sent.chat_id, sent.message_id, thread)

    def _conversation(self, message: Message, question: str, replied_to_bot: bool) -> list[ChatTurn]:
        user_turn = ChatTurn("user", f"[Сообщение от {_author(message)}]\n{question}")
        quoted = message.reply_to_message
        if replied_to_bot:
            history = self._memory.history_for(quoted.chat_id, quoted.message_id)
            if history is None:
                # Sin memoria (p. ej. tras reiniciar): al menos su propio mensaje.
                history = [ChatTurn("model", quoted.text or quoted.caption or "")]
            return [*history, user_turn]

        quoted_text = quoted.text or quoted.caption if quoted else None
        if quoted_text:
            return [ChatTurn("user", (
                f"[Цитируемое сообщение от {_author(quoted)}]\n{quoted_text}\n\n{user_turn.text}"
            ))]
        return [user_turn]


def _is_reply_to(message: Message, bot_id: int) -> bool:
    quoted = message.reply_to_message
    return bool(quoted and quoted.from_user and quoted.from_user.id == bot_id)


def _author(message: Message) -> str:
    return message.from_user.full_name if message.from_user else "Участник"


def _mentions(message: Message, bot_username: str) -> bool:
    target = f"@{bot_username}".lower()
    return any(
        text.lower() == target
        for text in message.parse_entities([MessageEntityType.MENTION]).values()
    )


def _strip_mention(text: str, bot_username: str) -> str:
    target = f"@{bot_username}"
    index = text.lower().find(target.lower())
    while index != -1:
        text = text[:index] + text[index + len(target):]
        index = text.lower().find(target.lower())
    return text.strip(" \n,:")


def _split(text: str, limit: int) -> list[str]:
    chunks: list[str] = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut <= 0:
            cut = limit
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")
    if text:
        chunks.append(text)
    return chunks
