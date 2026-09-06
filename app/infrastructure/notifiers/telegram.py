import logging

from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(
        self,
        token: str,
        chat_id: str,
        thread_id: int | None = None,
        parse_mode: ParseMode | None = None,
    ) -> None:
        self._bot = Bot(token=token)
        self._chat_id = chat_id
        self._thread_id = thread_id
        self._parse_mode = parse_mode

    async def send(self, text: str) -> None:
        try:
            await self._bot.send_message(
                chat_id=self._chat_id,
                text=text,
                message_thread_id=self._thread_id,
                parse_mode=self._parse_mode,
            )
            logger.info("Enviado: %s", text)
        except TelegramError as exc:
            logger.error("Fallo al enviar %r: %s", text, exc)