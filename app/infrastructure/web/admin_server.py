"""Panel de administracion (aiohttp).

Rutas publicas:
    /                         -> landing (estetica BRAINBIZZ)
    /login                    -> formulario de acceso
    /static/...               -> css/js/imagenes
Rutas protegidas (sesion con role=admin):
    /admin                    -> dashboard (inicio del panel)
    /admin/location           -> configure the town/city
    /admin/location/confirm   -> confirm town when the search is ambiguous
    /admin/alerts             -> enable/disable tracked price-alert instruments
    /admin/ai                 -> AI assistant identity (Gemini) + test prompt

Vistas en resources/views/ (Jinja2), assets en resources/static/. Este modulo
solo orquesta: arma el contexto y delega el render en ViewRenderer.
Presentacion pura, sin logica de dominio.
"""
from __future__ import annotations

from pathlib import Path

from aiohttp import web

from application.ports.language_model import LanguageModelError
from application.ports.municipality_directory import MunicipalityDirectory
from application.services.ai_persona_service import AiPersonaService
from application.services.instrument_settings_service import InstrumentSettingsService
from application.services.location_service import LocationService
from application.services.user_service import UserService
from application.services.uptime_service import UptimeService
from application.use_cases.answer_mention import AnswerMention
from domain.value_objects.ai_persona import MAX_SYSTEM_INSTRUCTION_LENGTH, AiPersona
from domain.value_objects.chat_turn import ChatTurn
from domain.value_objects.municipality import Municipality
from infrastructure.config.instruments import INSTRUMENTS
from infrastructure.web.session_store import SessionStore
from infrastructure.web.view_renderer import ViewRenderer

_MAX_RESULTS_SHOWN = 20
_SESSION_COOKIE = "session"
_SESSION_MAX_AGE = 8 * 60 * 60  # 8 horas
_ADMIN_ROLE = "admin"
_PUBLIC_PATHS = {"/", "/login", "/logout", "/health"}

_ALERT_CATEGORY_ORDER = ["us_stock", "us_etf", "crypto", "ru_stock", "fx"]
_ALERT_CATEGORY_LABELS = {
    "us_stock": "Acciones (Magníficas)",
    "us_etf": "Fondos (ETF)",
    "crypto": "Criptomonedas",
    "ru_stock": "Acciones MOEX",
    "fx": "Divisas",
}

# app/infrastructure/web/admin_server.py -> parents[2] = app/
_STATIC_DIR = Path(__file__).resolve().parents[2] / "resources" / "static"


def _location_context(location: LocationService, message: str = "", message_class: str = "") -> dict:
    m = location.current
    return {
        "active": "location",
        "message": message,
        "message_class": message_class,
        "current_ine": m.ine,
        "current_name": m.name,
    }


def _alerts_context(instrument_settings: InstrumentSettingsService, message: str = "", message_class: str = "") -> dict:
    grouped: dict[str, list[dict]] = {category: [] for category in _ALERT_CATEGORY_ORDER}
    for instrument in INSTRUMENTS:
        grouped[instrument.category].append({
            "symbol": instrument.symbol,
            "label": instrument.label,
            "enabled": instrument_settings.is_enabled(instrument.symbol),
        })
    return {
        "active": "alerts",
        "message": message,
        "message_class": message_class,
        "categories": [
            {"label": _ALERT_CATEGORY_LABELS[category], "instruments": grouped[category]}
            for category in _ALERT_CATEGORY_ORDER
        ],
    }


def _ai_context(
    persona: AiPersona,
    available: bool,
    message: str = "",
    message_class: str = "",
    test_prompt: str = "",
    test_answer: str = "",
) -> dict:
    return {
        "active": "ai",
        "message": message,
        "message_class": message_class,
        "persona": persona,
        "available": available,
        "max_length": MAX_SYSTEM_INSTRUCTION_LENGTH,
        "test_prompt": test_prompt,
        "test_answer": test_answer,
    }


def _user_context(request: web.Request) -> dict:
    user = request.get("user")
    if user is None:
        return {}
    return {
        "user_name": user.name,
        "user_initial": user.name[:1].upper(),
        "avatar": user.avatar,
    }


def _is_authenticated(request: web.Request, sessions: SessionStore) -> bool:
    token = request.cookies.get(_SESSION_COOKIE)
    return bool(token and sessions.username_for(token))


def _auth_middleware(user_service: UserService, sessions: SessionStore):
    @web.middleware
    async def middleware(request: web.Request, handler):
        if request.path in _PUBLIC_PATHS or request.path.startswith("/static/"):
            return await handler(request)

        token = request.cookies.get(_SESSION_COOKIE)
        username = sessions.username_for(token) if token else None
        user = await user_service.get_by_name(username) if username else None

        if user is None or user.role.value != _ADMIN_ROLE:
            raise web.HTTPFound("/login")

        request["user"] = user
        return await handler(request)

    return middleware


def build_admin_app(
    location: LocationService,
    municipality_directory: MunicipalityDirectory,
    user_service: UserService,
    uptime_service: UptimeService,
    instrument_settings: InstrumentSettingsService,
    ai_personas: AiPersonaService,
    answer_mention: AnswerMention | None,
    renderer: ViewRenderer | None = None,
) -> web.Application:
    sessions = SessionStore()
    renderer = renderer or ViewRenderer()
    app = web.Application(middlewares=[_auth_middleware(user_service, sessions)])

    def html_response(template: str, **context) -> web.Response:
        return web.Response(text=renderer.render(template, **context), content_type="text/html")

    # ---------------- publico ----------------
    async def landing(request: web.Request) -> web.Response:
        return html_response("landing.html", authenticated=_is_authenticated(request, sessions))

    async def login_get(request: web.Request) -> web.Response:
        if _is_authenticated(request, sessions):
            raise web.HTTPFound("/admin")
        return html_response("login.html", authenticated=False)

    async def login_post(request: web.Request) -> web.Response:
        data = await request.post()
        name = str(data.get("name", "")).strip()
        password = str(data.get("password", ""))

        user = await user_service.authenticate(name, password)
        if user is None:
            return html_response("login.html", authenticated=False,
                                 error="Usuario o contraseña incorrectos.")
        if user.role.value != _ADMIN_ROLE:
            return html_response("login.html", authenticated=False,
                                 error="Este usuario no tiene permiso de administrador.")

        token = sessions.create(user.name)
        response = web.HTTPFound("/admin")
        response.set_cookie(_SESSION_COOKIE, token, max_age=_SESSION_MAX_AGE, httponly=True, samesite="Lax")
        raise response

    async def logout_post(request: web.Request) -> web.Response:
        token = request.cookies.get(_SESSION_COOKIE)
        if token:
            sessions.destroy(token)
        response = web.HTTPFound("/")
        response.del_cookie(_SESSION_COOKIE)
        raise response

    # ---------------- admin: dashboard ----------------
    async def dashboard(request: web.Request) -> web.Response:
        m = location.current
        return html_response(
            "admin/dashboard.html",
            active="dashboard",
            current_ine=m.ine,
            current_name=m.name,
            uptime=uptime_service.uptime_human(),
            **_user_context(request),
        )

    # ---------------- admin: location ----------------
    async def location_get(request: web.Request) -> web.Response:
        return html_response("admin/location.html", **_location_context(location), **_user_context(request))

    async def location_post(request: web.Request) -> web.Response:
        data = await request.post()
        query = str(data.get("nombre", "")).strip()
        if len(query) < 2:
            return html_response("admin/location.html",
                                 **_location_context(location, "Escribe al menos 2 letras.", "err"), **_user_context(request))

        results = await municipality_directory.search(query)
        if not results:
            return html_response("admin/location.html",
                                 **_location_context(location, f'No se encontró ningún municipio llamado "{query}".', "err"), **_user_context(request))
        if len(results) == 1:
            await location.change(results[0].municipality)
            name = results[0].municipality.name
            return html_response("admin/location.html",
                                 **_location_context(location, f"Guardado: {name}.", "ok"), **_user_context(request))
        if len(results) > _MAX_RESULTS_SHOWN:
            return html_response("admin/location.html",
                                 **_location_context(location, f'Demasiados resultados ({len(results)}) para "{query}". Escribe un nombre más específico.', "err"), **_user_context(request))
        return html_response("admin/candidates.html", active="location", query=query, results=results, **_user_context(request))

    async def location_confirm(request: web.Request) -> web.Response:
        data = await request.post()
        ine = str(data.get("ine", "")).strip()
        name = str(data.get("name", "")).strip() or None
        try:
            municipality = Municipality(ine=ine, name=name)
        except ValueError:
            return html_response("admin/location.html",
                                 **_location_context(location, "Selección inválida.", "err"), **_user_context(request))
        await location.change(municipality)
        return html_response("admin/location.html",
                             **_location_context(location, f"Guardado: {name or ine}.", "ok"), **_user_context(request))

    # ---------------- admin: alertas de precio ----------------
    async def alerts_get(request: web.Request) -> web.Response:
        return html_response("admin/alerts.html", **_alerts_context(instrument_settings), **_user_context(request))

    async def alerts_post(request: web.Request) -> web.Response:
        data = await request.post()
        enabled_symbols = set(data.getall("enabled", []))
        await instrument_settings.apply_enabled_symbols(enabled_symbols)
        return html_response(
            "admin/alerts.html",
            **_alerts_context(instrument_settings, "Cambios guardados.", "ok"),
            **_user_context(request),
        )

    # ---------------- admin: asistente IA ----------------
    async def ai_get(request: web.Request) -> web.Response:
        return html_response(
            "admin/ai.html", **_ai_context(ai_personas.current, answer_mention is not None), **_user_context(request)
        )

    async def ai_post(request: web.Request) -> web.Response:
        data = await request.post()
        available = answer_mention is not None
        try:
            persona = AiPersona(
                system_instruction=str(data.get("system_instruction", "")).replace("\r\n", "\n").strip(),
                model=str(data.get("model", "")).strip().lower(),
                enabled=data.get("enabled") == "on",
            )
        except ValueError as exc:
            return html_response(
                "admin/ai.html", **_ai_context(ai_personas.current, available, str(exc), "err"), **_user_context(request)
            )

        if data.get("action") != "test":
            await ai_personas.change(persona)
            return html_response(
                "admin/ai.html", **_ai_context(persona, available, "Identidad guardada.", "ok"), **_user_context(request)
            )

        # Probar: usa lo escrito en el formulario SIN guardarlo.
        test_prompt = str(data.get("test_prompt", "")).strip()
        if not available:
            return html_response("admin/ai.html", **_ai_context(
                persona, available, "Falta GEMINI_API_KEY en el .env.", "err", test_prompt), **_user_context(request))
        if not test_prompt:
            return html_response("admin/ai.html", **_ai_context(
                persona, available, "Escribe un mensaje de prueba.", "err"), **_user_context(request))
        try:
            answer = await answer_mention.execute([ChatTurn("user", test_prompt)], persona)
        except LanguageModelError as exc:
            return html_response("admin/ai.html", **_ai_context(
                persona, available, str(exc), "err", test_prompt), **_user_context(request))
        return html_response("admin/ai.html", **_ai_context(
            persona, available, "Prueba realizada (sin guardar).", "ok", test_prompt, answer), **_user_context(request))

    async def health(request: web.Request) -> web.Response:
        return web.Response(text="ok")

    app.router.add_get("/", landing)
    app.router.add_get("/login", login_get)
    app.router.add_post("/login", login_post)
    app.router.add_post("/logout", logout_post)
    app.router.add_get("/admin", dashboard)
    app.router.add_get("/admin/location", location_get)
    app.router.add_post("/admin/location", location_post)
    app.router.add_post("/admin/location/confirm", location_confirm)
    app.router.add_get("/admin/alerts", alerts_get)
    app.router.add_post("/admin/alerts", alerts_post)
    app.router.add_get("/admin/ai", ai_get)
    app.router.add_post("/admin/ai", ai_post)
    app.router.add_get("/health", health)
    app.router.add_static("/static/", _STATIC_DIR)
    return app


class AdminServer:
    def __init__(self, app: web.Application, host: str, port: int) -> None:
        self._app, self._host, self._port = app, host, port
        self._runner: web.AppRunner | None = None

    async def start(self) -> None:
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        await web.TCPSite(self._runner, self._host, self._port).start()

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None