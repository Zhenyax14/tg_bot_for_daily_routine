import logging

from telegram.ext import Application, CommandHandler

from application.ports.notifier import Notifier
from application.use_cases.get_world_times import GetWorldTimes
from application.use_cases.schedule_daily_messages import ScheduleDailyMessages
from application.use_cases.send_message import SendMessage
from config.errors import ConfigError
from config.settings import Settings
from infrastructure.config.cities import WORLD_CLOCK_CITIES
from infrastructure.notifiers.console import ConsoleNotifier
from infrastructure.notifiers.telegram import TelegramNotifier
from infrastructure.persistence.static_message_repository import StaticMessageRepository
from infrastructure.scheduling.apscheduler_adapter import APSchedulerAdapter
from infrastructure.telegram.commands.time_command import TimeCommand
from infrastructure.time.system_clock import SystemClock

logger = logging.getLogger("bot")


def build_notifier(settings: Settings) -> Notifier:
    if settings.dry_run:
        logger.warning("DRY_RUN activo: no se envía nada a Telegram")
        return ConsoleNotifier()
    return TelegramNotifier(settings.bot_token, settings.chat_id, settings.thread_id)


def build_application(settings: Settings) -> Application:
    notifier = build_notifier(settings)
    scheduler = APSchedulerAdapter(settings.timezone)
    repository = StaticMessageRepository()

    send_message = SendMessage(notifier)
    ScheduleDailyMessages(repository, scheduler, send_message).execute()

    clock = SystemClock()
    time_cmd = TimeCommand(GetWorldTimes(clock, WORLD_CLOCK_CITIES))

    async def _post_init(app: Application) -> None:
        await send_message.execute(settings.startup_message)
        scheduler.start()
        logger.info("Bot arrancado (%s)", settings.timezone)

    async def _post_shutdown(app: Application) -> None:
        scheduler.shutdown()
        logger.info("Parado limpiamente")

    application = (
        Application.builder()
        .token(settings.bot_token)
        .post_init(_post_init)
        .post_shutdown(_post_shutdown)
        .build()
    )
    application.add_handler(CommandHandler("time", time_cmd))
    return application


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s | %(message)s",
    )
    try:
        settings = Settings.from_env()
        application = build_application(settings)
        application.run_polling()
    except ConfigError as exc:
        logger.error("%s", exc)
        raise SystemExit(1)


if __name__ == "__main__":
    main()