import logging

from telegram.ext import Application, CommandHandler

from application.ports.notifier import Notifier
from application.use_cases.announce_todays_holidays import AnnounceTodaysHolidays
from application.use_cases.get_todays_holidays import GetTodaysHolidays
from application.use_cases.get_world_times import GetWorldTimes
from application.use_cases.schedule_daily_messages import ScheduleDailyMessages
from application.use_cases.send_message import SendMessage
from config.errors import ConfigError
from config.settings import Settings
from domain.value_objects.daily_time import DailyTime
from infrastructure.config.cities import WORLD_CLOCK_CITIES
from infrastructure.holidays.nager_date import NagerDateHolidayProvider
from infrastructure.notifiers.console import ConsoleNotifier
from infrastructure.notifiers.telegram import TelegramNotifier
from infrastructure.persistence.static_message_repository import StaticMessageRepository
from infrastructure.scheduling.apscheduler_adapter import APSchedulerAdapter
from infrastructure.telegram.commands.time_command import TimeCommand
from infrastructure.telegram.holiday_formatting import format_holiday_greeting
from infrastructure.time.system_clock import SystemClock

logger = logging.getLogger("bot")

# Se felicita un minuto despues del mensaje matutino ("morning-greeting", 07:00),
# para que caiga justo detras de el. Si cambias la hora del "buenos dias", ajusta esta.
HOLIDAY_GREETING_AT = DailyTime(7, 1)


def build_notifier(settings: Settings) -> Notifier:
    if settings.dry_run:
        logger.warning("DRY_RUN activo: no se envía nada a Telegram")
        return ConsoleNotifier()
    return TelegramNotifier(settings.bot_token, settings.chat_id, settings.thread_id)


def build_application(settings: Settings) -> Application:
    notifier = build_notifier(settings)
    scheduler = APSchedulerAdapter(settings.timezone)
    repository = StaticMessageRepository()
    clock = SystemClock()

    send_message = SendMessage(notifier)

    # Mensajes diarios estaticos (comportamiento existente)
    ScheduleDailyMessages(repository, scheduler, send_message).execute()

    # Felicitacion de festivos: justo despues del "buenos dias"
    announce_holidays = AnnounceTodaysHolidays(
        GetTodaysHolidays(NagerDateHolidayProvider(), clock),
        send_message,
        format_holiday_greeting,
    )
    scheduler.schedule_daily(
        job_id="holidays-greeting",
        at=HOLIDAY_GREETING_AT,
        job=announce_holidays.execute,
    )
    logger.info("Programado holidays-greeting a las %s", HOLIDAY_GREETING_AT)

    # Comando /time
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