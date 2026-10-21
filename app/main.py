import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from application.ports.notifier import Notifier
from application.services.ai_persona_service import AiPersonaService
from application.services.conversation_memory import ConversationMemory
from application.services.instrument_settings_service import InstrumentSettingsService
from application.services.knowledge_base import KnowledgeBase
from application.services.location_service import LocationService
from application.services.reference_prices import ReferencePrices
from application.services.squad_persona_service import SquadPersonaService
from application.services.squad_topics import SquadTopics
from application.services.uptime_service import UptimeService
from application.services.user_service import UserService
from application.use_cases.answer_mention import AnswerMention
from application.use_cases.announce_todays_holidays import AnnounceTodaysHolidays
from application.use_cases.bootstrap_admin_user import BootstrapAdminUser
from application.use_cases.check_price_movements import CheckPriceMovements
from application.use_cases.get_todays_holidays import GetTodaysHolidays
from application.use_cases.get_upcoming_holidays import GetUpcomingHolidays
from application.use_cases.get_world_times import GetWorldTimes
from application.use_cases.run_squad_conversation import RunSquadConversation
from application.use_cases.schedule_daily_messages import ScheduleDailyMessages
from application.use_cases.send_message import SendMessage
from config.errors import ConfigError
from config.settings import Settings
from domain.services.price_movement_policy import PriceMovementPolicy
from domain.value_objects.daily_time import DailyTime
from domain.value_objects.municipality import Municipality
from infrastructure.ai.gemini_language_model import GeminiLanguageModel
from infrastructure.ai.gemini_model_catalog import GeminiModelCatalog
from infrastructure.config.cities import WORLD_CLOCK_CITIES
from infrastructure.config.instruments import INSTRUMENTS
from infrastructure.documents.file_text_extractor import FileTextExtractor
from infrastructure.holidays.country_routing import CountryRoutingHolidayProvider
from infrastructure.holidays.festivos_io import FestivosIoHolidayProvider
from infrastructure.holidays.nager_date import NagerDateHolidayProvider
from infrastructure.location.festivos_io_municipality_directory import FestivosIoMunicipalityDirectory
from infrastructure.notifiers.console import ConsoleNotifier
from infrastructure.notifiers.telegram import TelegramNotifier
from infrastructure.persistence.database import Database
from infrastructure.persistence.postgres_ai_persona_repository import PostgresAiPersonaRepository
from infrastructure.persistence.postgres_instrument_settings_repository import (
    PostgresInstrumentSettingsRepository,
)
from infrastructure.persistence.postgres_knowledge_document_repository import (
    PostgresKnowledgeDocumentRepository,
)
from infrastructure.persistence.postgres_location_repository import PostgresLocationRepository
from infrastructure.persistence.postgres_squad_persona_repository import PostgresSquadPersonaRepository
from infrastructure.persistence.postgres_user_repository import PostgresUserRepository
from infrastructure.persistence.static_message_repository import StaticMessageRepository
from infrastructure.quotes.moex_quote_provider import MoexQuoteProvider
from infrastructure.quotes.movement_formatting import format_movement_alert
from infrastructure.quotes.routing_quote_provider import RoutingQuoteProvider
from infrastructure.quotes.yahoo_finance_quote_provider import YahooFinanceQuoteProvider
from infrastructure.scheduling.apscheduler_adapter import APSchedulerAdapter
from infrastructure.security.bcrypt_password_hasher import BcryptPasswordHasher
from infrastructure.telegram.ai_mention_handler import ALBUM_IMAGES, AiMentionHandler
from infrastructure.telegram.commands.holidays_command import HolidaysCommand
from infrastructure.telegram.commands.time_command import TimeCommand
from infrastructure.telegram.holiday_formatting import format_holiday_greeting
from infrastructure.telegram.squad_message_handler import SquadMessageHandler
from infrastructure.telegram.telegram_squad_gateway import TelegramSquadGateway
from infrastructure.time.system_clock import SystemClock
from infrastructure.web.admin_server import AdminServer, build_admin_app

PRICE_ALERTS_CHECK_INTERVAL_MINUTES = 5

logger = logging.getLogger("bot")

HOLIDAY_GREETING_AT = DailyTime(7, 1)  # justo tras el "buenos dias" de las 07:00


def build_notifier(settings: Settings) -> Notifier:
    if settings.dry_run:
        logger.warning("DRY_RUN activo: no se envía nada a Telegram")
        return ConsoleNotifier()
    return TelegramNotifier(settings.bot_token, settings.chat_id, settings.thread_id)


def build_price_alerts_notifier(settings: Settings) -> Notifier:
    if settings.dry_run:
        return ConsoleNotifier()
    return TelegramNotifier(
        settings.bot_token,
        settings.chat_id,
        settings.price_alerts_thread_id,
        parse_mode=ParseMode.HTML,
    )


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

    uptime_service = UptimeService(time.monotonic)

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

    # Alertas de movimientos de precio (±5% en trail, reinicio diario) en el
    # hilo dedicado del mismo grupo, cada 5 minutos.
    price_alerts_notifier = build_price_alerts_notifier(settings)
    send_price_alert = SendMessage(price_alerts_notifier)
    yahoo_finance_provider = YahooFinanceQuoteProvider()
    moex_provider = MoexQuoteProvider()
    routing_quote_provider = RoutingQuoteProvider(
        {"us": yahoo_finance_provider, "crypto": yahoo_finance_provider, "ru": moex_provider, "fx": moex_provider}
    )
    reference_prices = ReferencePrices(lambda: datetime.now(ZoneInfo(settings.timezone)).date())
    movement_policy = PriceMovementPolicy(5.0)
    instrument_settings = InstrumentSettingsService(
        PostgresInstrumentSettingsRepository(database), INSTRUMENTS
    )

    async def alert_price_movement(instrument, movement) -> None:
        await send_price_alert.execute(format_movement_alert(instrument, movement))

    check_price_movements = CheckPriceMovements(
        instrument_settings, routing_quote_provider, reference_prices, movement_policy, alert_price_movement
    )
    scheduler.schedule_interval(
        job_id="price-alerts",
        minutes=PRICE_ALERTS_CHECK_INTERVAL_MINUTES,
        job=check_price_movements.execute,
    )

    # Asistente IA (Gemini): responde a @menciones en el hilo General. La
    # identidad (instrucciones + modelo) vive en BBDD y se edita en /admin/ai.
    ai_personas = AiPersonaService(PostgresAiPersonaRepository(database))
    knowledge = KnowledgeBase(PostgresKnowledgeDocumentRepository(database), FileTextExtractor())
    answer_mention: AnswerMention | None = None
    model_catalog: GeminiModelCatalog | None = None
    if settings.gemini_api_key:
        answer_mention = AnswerMention(ai_personas, GeminiLanguageModel(settings.gemini_api_key), knowledge)
        model_catalog = GeminiModelCatalog(settings.gemini_api_key)
    else:
        logger.warning("GEMINI_API_KEY vacia: asistente IA desactivado")

    # Topic multi-bot: hasta 3 bots, cada uno con su token, su clave de Gemini
    # y su identidad (personalidad + meta secreta, en /admin/squad). Corren en
    # este mismo proceso, cada uno con su propia Application de Telegram.
    squad_personas = SquadPersonaService(PostgresSquadPersonaRepository(database))
    squad_gateway = TelegramSquadGateway(int(settings.chat_id), settings.squad_thread_id)
    squad_bots = [] if settings.dry_run else [b for b in settings.squad_bots if b.token and b.gemini_api_key]
    for bot in settings.squad_bots:
        if bool(bot.token) != bool(bot.gemini_api_key):
            logger.warning("Bot %s del topic sin AI_BOT_%s_TOKEN o sin AI_BOT_%s_GEMINI_KEY: no arranca",
                           bot.slot, bot.slot, bot.slot)
    squad_conversation = RunSquadConversation(
        squad_personas,
        {bot.slot: GeminiLanguageModel(bot.gemini_api_key) for bot in squad_bots},
        squad_gateway,
        SquadTopics(),
    )
    squad_apps: dict[int, Application] = {}
    for bot in squad_bots:
        squad_app = Application.builder().token(bot.token).build()
        squad_app.add_handler(MessageHandler(
            filters.Chat(chat_id=int(settings.chat_id)) & ~filters.COMMAND & (filters.TEXT | filters.CAPTION),
            SquadMessageHandler(bot.slot, squad_conversation, squad_gateway),
        ))
        squad_apps[bot.slot] = squad_app
    squad_model_catalog = model_catalog or (GeminiModelCatalog(squad_bots[0].gemini_api_key) if squad_bots else None)
    started_squad_apps: list[Application] = []

    time_cmd = TimeCommand(GetWorldTimes(clock, WORLD_CLOCK_CITIES))
    holidays_cmd = HolidaysCommand(GetUpcomingHolidays(holiday_provider, clock))

    # Panel de administracion: login real (usuario+contrasena) contra la
    # tabla users, sesion por cookie, busqueda de municipio por nombre.
    municipality_directory = FestivosIoMunicipalityDirectory()
    admin_app = build_admin_app(
        location, municipality_directory, user_service, uptime_service, instrument_settings,
        ai_personas, answer_mention, model_catalog, knowledge,
        squad_personas, squad_gateway.members, squad_model_catalog,
    )
    admin_server = AdminServer(admin_app, settings.web_host, settings.web_port)

    async def _post_init(app: Application) -> None:
        await database.connect()
        await database.init_schema()
        await location.load()
        await instrument_settings.load()
        await ai_personas.load()
        await knowledge.load()
        await squad_personas.load()
        # ADMIN_USER/ADMIN_PASSWORD siembran el PRIMER usuario admin (solo si
        # la tabla users esta vacia); no vuelven a tocarla despues.
        await bootstrap_admin.execute(
            settings.admin_user, settings.admin_password, settings.admin_role
        )
        if settings.startup_message.strip():
            await send_message.execute(settings.startup_message)
        await send_price_alert.execute("✅ Система ценовых алертов запущена.")
        uptime_service.mark_started()
        scheduler.start()
        await admin_server.start()
        for slot, squad_app in squad_apps.items():
            # Un token invalido no debe tumbar el bot principal ni a los demas.
            try:
                await squad_app.initialize()
                await squad_app.start()
                await squad_app.updater.start_polling()
                member = squad_gateway.register(slot, squad_app.bot)
            except Exception:
                logger.exception("Bot %s del topic no pudo arrancar", slot)
                continue
            started_squad_apps.append(squad_app)
            logger.info("Bot %s del topic conectado como @%s", slot, member.username)
        logger.info(
            "Bot arrancado (%s), panel en http://%s:%s, localidad ES=%s",
            settings.timezone, settings.web_host, settings.web_port, location.current.ine,
        )

    async def _post_shutdown(app: Application) -> None:
        await squad_conversation.close()
        for squad_app in started_squad_apps:
            await squad_app.updater.stop()
            await squad_app.stop()
            await squad_app.shutdown()
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
    if answer_mention is not None:
        application.add_handler(MessageHandler(
            filters.Chat(chat_id=int(settings.chat_id)) & ~filters.COMMAND
            & (
                (filters.TEXT | filters.PHOTO | filters.Document.IMAGE)
                & (filters.Entity("mention") | filters.CaptionEntity("mention") | filters.REPLY)
                | ALBUM_IMAGES
            ),
            AiMentionHandler(answer_mention, ConversationMemory()),
        ))
    return application


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s | %(message)s",
    )
    # httpx registra cada URL en INFO, y las de la API de Telegram llevan el
    # token del bot dentro (/bot<TOKEN>/...): nunca debe acabar en los logs.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        settings = Settings.from_env()
        application = build_application(settings)
        application.run_polling()
    except ConfigError as exc:
        logger.error("%s", exc)
        raise SystemExit(1)


if __name__ == "__main__":
    main()