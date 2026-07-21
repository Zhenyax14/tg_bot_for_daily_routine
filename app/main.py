import asyncio
import logging
import signal

from application.ports.notifier import Notifier
from application.use_cases.schedule_daily_messages import ScheduleDailyMessages
from application.use_cases.send_message import SendMessage
from config.errors import ConfigError
from config.settings import Settings
from infrastructure.notifiers.console import ConsoleNotifier
from infrastructure.notifiers.telegram import TelegramNotifier
from infrastructure.persistence.static_message_repository import StaticMessageRepository
from infrastructure.scheduling.apscheduler_adapter import APSchedulerAdapter

logger = logging.getLogger("bot")


def build_notifier(settings: Settings) -> Notifier:
    if settings.dry_run:
        logger.warning("DRY_RUN activo: no se envía nada a Telegram")
        return ConsoleNotifier()
    return TelegramNotifier(settings.bot_token, settings.chat_id, settings.thread_id)


async def _wait_for_shutdown() -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    await stop.wait()


async def run() -> None:
    settings = Settings.from_env()

    notifier = build_notifier(settings)
    scheduler = APSchedulerAdapter(settings.timezone)
    repository = StaticMessageRepository()

    send_message = SendMessage(notifier)
    ScheduleDailyMessages(repository, scheduler, send_message).execute()

    await send_message.execute(settings.startup_message)
    scheduler.start()
    logger.info("Bot arrancado (%s)", settings.timezone)

    await _wait_for_shutdown()
    scheduler.shutdown()
    logger.info("Parado limpiamente")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s | %(message)s",
    )
    try:
        asyncio.run(run())
    except ConfigError as exc:
        logger.error("%s", exc)
        raise SystemExit(1)


if __name__ == "__main__":
    main()