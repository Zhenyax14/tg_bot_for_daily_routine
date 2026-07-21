import logging

logger = logging.getLogger(__name__)


class ConsoleNotifier:
    async def send(self, text: str) -> None:
        logger.info("[DRY-RUN] %s", text)