import logging

from telegram.ext import Application, CommandHandler

from application.ports.notifier import Notifier
from application.services.location_service import LocationService
from application.services.user_service import UserService
from application.use_cases.announce_todays_holidays import AnnounceTodaysHolidays
from application.use_cases.bootstrap_admin_user import BootstrapAdminUser
from application.use_cases.get_todays_holidays import GetTodaysHolidays
from application.use_cases.get_upcoming_holidays import GetUpcomingHolidays
from application.use_cases.get_world_times import GetWorldTimes
from application.use_cases.schedule_daily_messages import ScheduleDailyMessages
from application.use_cases.send_message import SendMessage
from config.errors import ConfigError
from config.settings import Settings
from domain.value_objects.daily_time import DailyTime
from domain.value_objects.municipality import Municipality
from infrastructure.config.cities import WORLD_CLOCK_CITIES
from infrastructure.holidays.country_routing import CountryRoutingHolidayProvider
from infrastructure.holidays.festivos_io import FestivosIoHolidayProvider
from infrastructure.holidays.nager_date import NagerDateHolidayProvider
from infrastructure.location.festivos_io_municipality_directory import FestivosIoMunicipalityDirectory
from infrastructure.notifiers.console import ConsoleNotifier
from infrastructure.notifiers.telegram import TelegramNotifier
from infrastructure.persistence.database import Database
from infrastructure.persistence.postgres_location_repository import PostgresLocationRepository
from infrastructure.persistence.postgres_user_repository import PostgresUserRepository
from infrastructure.persistence.static_message_repository import StaticMessageRepository
from infrastructure.scheduling.apscheduler_adapter import APSchedulerAdapter
from infrastructure.security.bcrypt_password_hasher import BcryptPasswordHasher
from infrastructure.telegram.commands.holidays_command import HolidaysCommand
from infrastructure.telegram.commands.time_command import TimeCommand
from infrastructure.telegram.holiday_formatting import format_holiday_greeting
from infrastructure.time.system_clock import SystemClock
from infrastructure.web.admin_server import AdminServer, build_admin_app

logger = logging.getLogger("bot")

HOLIDAY_GREETING_AT = DailyTime(7, 1)  # justo tras el "buenos dias" de las 07:00


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

    # PostgreSQL: el pool se conecta en post_init (dentro del loop)
    database = Database(settings.database_url)

    location = LocationService(
        PostgresLocationRepository(database),
        default=Municipality(settings.spain_municipio),
    )

    user_repository = PostgresUserRepository(database)
    user_service = UserService(user_repository, BcryptPasswordHasher())
    bootstrap_admin = BootstrapAdminUser(user_repository, user_service)

    holiday_provider = CountryRoutingHolidayProvider(
        {
            "ES": FestivosIoHolidayProvider(lambda: location.current.ine),
            "RU": NagerDateHolidayProvider(),
        }
    )

    send_message = SendMessage(notifier)
    ScheduleDailyMessages(repository, scheduler, send_message).execute()

    announce_holidays = AnnounceTodaysHolidays(
        GetTodaysHolidays(holiday_provider, clock), send_message, format_holiday_greeting
    )
    scheduler.schedule_daily(
        job_id="holidays-greeting", at=HOLIDAY_GREETING_AT, job=announce_holidays.execute
    )

    time_cmd = TimeCommand(GetWorldTimes(clock, WORLD_CLOCK_CITIES))
    holidays_cmd = HolidaysCommand(GetUpcomingHolidays(holiday_provider, clock))

    # Panel de administracion: login real (usuario+contrasena) contra la
    # tabla users, sesion por cookie, busqueda de municipio por nombre.
    municipality_directory = FestivosIoMunicipalityDirectory()
    admin_app = build_admin_app(location, municipality_directory, user_service)
    admin_server = AdminServer(admin_app, settings.web_host, settings.web_port)

    async def _post_init(app: Application) -> None:
        await database.connect()
        await database.init_schema()
        await location.load()
        # ADMIN_USER/ADMIN_PASSWORD siembran el PRIMER usuario admin (solo si
        # la tabla users esta vacia); no vuelven a tocarla despues.
        await bootstrap_admin.execute(
            settings.admin_user, settings.admin_password, settings.admin_role
        )
        await send_message.execute(settings.startup_message)
        scheduler.start()
        await admin_server.start()
        logger.info(
            "Bot arrancado (%s), panel en http://%s:%s, localidad ES=%s",
            settings.timezone, settings.web_host, settings.web_port, location.current.ine,
        )

    async def _post_shutdown(app: Application) -> None:
        await admin_server.stop()
        scheduler.shutdown()
        await database.close()
        logger.info("Parado limpiamente")

    application = (
        Application.builder()
        .token(settings.bot_token)
        .post_init(_post_init)
        .post_shutdown(_post_shutdown)
        .build()
    )
    application.add_handler(CommandHandler("time", time_cmd))
    application.add_handler(CommandHandler("holidays", holidays_cmd))
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