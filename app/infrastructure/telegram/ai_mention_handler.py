"""Handler de menciones: en el hilo General del grupo, un mensaje que menciona
al bot (@nombrebot, en el texto o en el pie de una foto) o que responde a un
mensaje suyo se envia al modelo de lenguaje y la respuesta se publica como
reply.

Imagenes: se envian al modelo las fotos (y archivos de imagen sin comprimir)
del propio mensaje y, si es una mencion respondiendo a otra persona, tambien
las del mensaje citado ("@bot que ves aqui?" sobre un grafico ajeno). Los
albumes llegan como mensajes sueltos con el mismo media_group_id: se juntan
con AlbumCollector y se responden una sola vez, con todas sus imagenes.

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
from telegram.error import TelegramError
from telegram.ext import ContextTypes, filters

from application.ports.language_model import LanguageModelError
from application.services.conversation_memory import ConversationMemory
from application.use_cases.answer_mention import AnswerMention
from domain.value_objects.chat_turn import ChatTurn
from domain.value_objects.image_attachment import (
    MAX_IMAGE_BYTES,
    MAX_REQUEST_IMAGE_BYTES,
    ImageAttachment,
    ImageTooLarge,
    UnsupportedImageType,
)
from infrastructure.telegram.album_collector import AlbumCollector

logger = logging.getLogger(__name__)

_ERROR_REPLY = "⚠️ Не удалось получить ответ. Попробуйте позже."
_EMPTY_PROMPT_REPLY = "Слушаю 🙂 Напишите вопрос после упоминания."
_IMAGE_TOO_LARGE_REPLY = f"⚠️ Изображение слишком большое (максимум {MAX_IMAGE_BYTES // (1024 * 1024)} МБ)."
_IMAGE_UNSUPPORTED_REPLY = "⚠️ Этот формат изображения не поддерживается (подходят JPG, PNG, WEBP, HEIC)."
_IMAGE_DOWNLOAD_REPLY = "⚠️ Не удалось загрузить изображение."
_ALBUM_TOO_LARGE_REPLY = (
    f"⚠️ Изображения вместе слишком большие (максимум {MAX_REQUEST_IMAGE_BYTES // (1024 * 1024)} МБ). "
    "Отправьте меньше файлов или сжатые фото."
)
_TELEGRAM_PHOTO_MIME = "image/jpeg"  # Telegram recomprime toda "foto" a JPEG


class _ImageError(Exception):
    def __init__(self, reply: str) -> None:
        super().__init__(reply)
        self.reply = reply


class _AlbumImageFilter(filters.MessageFilter):
    """Deja pasar TODAS las imagenes de un album (aunque no lleven pie ni
    mencion): sin ellas no se puede juntar el album completo."""

    def filter(self, message: Message) -> bool:
        return bool(message.media_group_id) and _has_image(message)


ALBUM_IMAGES = _AlbumImageFilter()


class AiMentionHandler:
    def __init__(
        self, answer_mention: AnswerMention, memory: ConversationMemory, album_delay: float = 2.0
    ) -> None:
        self._answer_mention = answer_mention
        self._memory = memory
        self._albums = AlbumCollector(self._respond, album_delay)

    async def __call__(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        if message is None or not self._answer_mention.enabled:
            return
        if not (message.text or message.caption or _has_image(message)):
            return
        # Solo el hilo General: los mensajes dentro de un topic llevan is_topic_message.
        if message.is_topic_message:
            logger.debug("IA: ignorado, mensaje en el topic %s", message.message_thread_id)
            return
        if message.media_group_id:
            self._albums.add(message, context)
            return
        await self._respond([message], context)

    async def _respond(self, messages: list[Message], context: ContextTypes.DEFAULT_TYPE) -> None:
        """`messages` es un mensaje suelto o todas las piezas de un album."""
        bot_username = context.bot.username
        replying = next((m for m in messages if m.reply_to_message), None)
        quoted = replying.reply_to_message if replying else None
        replied_to_bot = replying is not None and _is_reply_to(replying, context.bot.id)
        lead = next((m for m in messages if _mentions(m, bot_username)), None)
        if lead is None and replied_to_bot:
            lead = replying
        if lead is None:
            return  # ni lo mencionan ni le responden (p. ej. un album ajeno)

        question = "\n".join(
            text for text in (_strip_mention(m.text or m.caption or "", bot_username) for m in messages) if text
        )
        logger.info(
            "IA: %s de %s (reply al bot=%s, imagenes propias=%d, cita=%s)",
            "respuesta" if replied_to_bot else "mencion", _author(lead), replied_to_bot,
            sum(_has_image(m) for m in messages), quoted is not None,
        )
        await context.bot.send_chat_action(chat_id=lead.chat_id, action=ChatAction.TYPING)
        try:
            own_images: tuple[ImageAttachment, ...] = ()
            for message in messages:
                own_images += await _images_of(message)
            if sum(len(image.data) for image in own_images) > MAX_REQUEST_IMAGE_BYTES:
                raise _ImageError(_ALBUM_TOO_LARGE_REPLY)
            conversation = await self._conversation(lead, quoted, question, replied_to_bot, own_images)
        except _ImageError as exc:
            logger.warning("IA: imagen rechazada: %s", exc.reply)
            await lead.reply_text(exc.reply)
            return

        if not question and not conversation[-1].images:
            await lead.reply_text(_EMPTY_PROMPT_REPLY)
            return

        try:
            answer = await self._answer_mention.execute(conversation)
        except LanguageModelError as exc:
            logger.error("IA: %s", exc)
            await lead.reply_text(_ERROR_REPLY)
            return

        logger.info(
            "IA: respondido (%d turnos, %d imagenes, %d caracteres)",
            len(conversation), sum(len(t.images) for t in conversation), len(answer),
        )
        thread = [*conversation, ChatTurn("model", answer)]
        for chunk in _split(answer, MessageLimit.MAX_TEXT_LENGTH):
            sent = await lead.reply_text(chunk)
            self._memory.remember(sent.chat_id, sent.message_id, thread)

    async def _conversation(
        self,
        lead: Message,
        quoted: Message | None,
        question: str,
        replied_to_bot: bool,
        own_images: tuple[ImageAttachment, ...],
    ) -> list[ChatTurn]:
        header = _header(f"Сообщение от {_author(lead)}", len(own_images))

        if replied_to_bot:
            history = self._memory.history_for(quoted.chat_id, quoted.message_id)
            if history is None:
                # Sin memoria (p. ej. tras reiniciar): al menos su propio mensaje.
                history = [ChatTurn("model", quoted.text or quoted.caption or "")]
            return [*history, ChatTurn("user", _join(header, question), own_images)]

        if quoted is None:
            return [ChatTurn("user", _join(header, question), own_images)]

        quoted_images = await _images_of(quoted)
        quoted_text = quoted.text or quoted.caption or ""
        if not (quoted_text or quoted_images):
            return [ChatTurn("user", _join(header, question), own_images)]
        quoted_header = _header(f"Цитируемое сообщение от {_author(quoted)}", len(quoted_images))
        text = _join(quoted_header, quoted_text) + "\n\n" + _join(header, question)
        return [ChatTurn("user", text, quoted_images + own_images)]


def _header(label: str, image_count: int) -> str:
    return f"[{label}, изображений: {image_count}]" if image_count else f"[{label}]"


def _join(header: str, body: str) -> str:
    return f"{header}\n{body}" if body else header


def _has_image(message: Message) -> bool:
    return bool(message.photo) or bool(
        message.document and (message.document.mime_type or "").startswith("image/")
    )


async def _images_of(message: Message) -> tuple[ImageAttachment, ...]:
    """Descarga la foto (la resolucion mas alta) o el archivo de imagen."""
    if message.photo:
        source, mime_type, size = message.photo[-1], _TELEGRAM_PHOTO_MIME, message.photo[-1].file_size
    elif message.document and (message.document.mime_type or "").startswith("image/"):
        source, mime_type, size = message.document, message.document.mime_type, message.document.file_size
    else:
        return ()

    if size and size > MAX_IMAGE_BYTES:
        raise _ImageError(_IMAGE_TOO_LARGE_REPLY)
    try:
        telegram_file = await source.get_file()
        data = bytes(await telegram_file.download_as_bytearray())
    except TelegramError as exc:
        logger.error("IA: fallo al descargar imagen: %s", exc)
        raise _ImageError(_IMAGE_DOWNLOAD_REPLY) from exc
    try:
        return (ImageAttachment(mime_type, data),)
    except ImageTooLarge as exc:
        raise _ImageError(_IMAGE_TOO_LARGE_REPLY) from exc
    except UnsupportedImageType as exc:
        raise _ImageError(_IMAGE_UNSUPPORTED_REPLY) from exc


def _is_reply_to(message: Message, bot_id: int) -> bool:
    quoted = message.reply_to_message
    return bool(quoted and quoted.from_user and quoted.from_user.id == bot_id)


def _author(message: Message) -> str:
    return message.from_user.full_name if message.from_user else "Участник"


def _mentions(message: Message, bot_username: str) -> bool:
    target = f"@{bot_username}".lower()
    found = {
        **message.parse_entities([MessageEntityType.MENTION]),
        **message.parse_caption_entities([MessageEntityType.MENTION]),
    }
    return any(text.lower() == target for text in found.values())


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
