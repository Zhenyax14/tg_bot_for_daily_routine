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
    /admin/ai                 -> AI assistant identity + context + model (Gemini)
    /admin/ai/documents       -> upload knowledge-base documents
    /admin/ai/documents/{id}/toggle|delete|download
    /admin/squad              -> the 3 topic bots: personality + secret goal + model

Vistas en resources/views/ (Jinja2), assets en resources/static/. Este modulo
solo orquesta: arma el contexto y delega el render en ViewRenderer.
Presentacion pura, sin logica de dominio.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Mapping
from urllib.parse import quote

from aiohttp import web

from application.ports.model_catalog import ModelCatalog, ModelCatalogError, ModelInfo
from application.ports.municipality_directory import MunicipalityDirectory
from application.services.ai_persona_service import AiPersonaService
from application.services.instrument_settings_service import InstrumentSettingsService
from application.services.knowledge_base import KnowledgeBase, KnowledgeBaseError
from application.services.location_service import LocationService
from application.services.squad_persona_service import SquadPersonaService
from application.services.user_service import UserService
from application.services.uptime_service import UptimeService
from application.use_cases.answer_mention import AnswerMention
from application.use_cases.run_squad_conversation import MAX_MESSAGES_PER_BOT_PER_TOPIC
from domain.value_objects.ai_persona import MAX_CONTEXT_LENGTH, MAX_SYSTEM_INSTRUCTION_LENGTH, AiPersona
from domain.entities.knowledge_document import CHARS_PER_TOKEN, KnowledgeDocument
from domain.value_objects.municipality import Municipality
from domain.value_objects.squad_message import SquadMember
from domain.value_objects.squad_persona import MAX_PERSONALITY_LENGTH, MAX_SECRET_GOAL_LENGTH, SquadPersona
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


def _model_groups(models: tuple[ModelInfo, ...], current: str) -> list[dict]:
    """Agrupa los modelos para los <optgroup> del desplegable. El modelo
    guardado siempre aparece, aunque Google ya no lo liste."""
    groups = {"stable": [], "alias": [], "preview": []}
    for model in models:
        if "preview" in model.id or "exp" in model.id:
            groups["preview"].append(model)
        elif model.id.endswith("-latest"):
            groups["alias"].append(model)
        else:
            groups["stable"].append(model)
    result = [
        {"label": label, "models": groups[key]}
        for key, label in (
            ("stable", "Estables"),
            ("alias", "Alias (Google los cambia de versión solo)"),
            ("preview", "Preview / experimentales"),
        )
        if groups[key]
    ]
    if current not in {m.id for m in models}:
        result.insert(0, {"label": "Guardado (no listado)", "models": [ModelInfo(current, current)]})
    return result


def _human_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.0f} KB"
    return f"{size / (1024 * 1024):.1f} MB".replace(".", ",")


def _thousands(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def _knowledge_context(knowledge: KnowledgeBase) -> dict:
    used = knowledge.enabled_chars()
    return {
        "documents": [
            {
                "id": d.id,
                "filename": d.filename,
                "size": _human_size(d.size_bytes),
                "tokens": _thousands(d.approx_tokens),
                "enabled": d.enabled,
                "uploaded": d.created_at.strftime("%d/%m/%Y"),
            }
            for d in knowledge.documents
        ],
        "knowledge_tokens": _thousands(used // CHARS_PER_TOKEN),
        "knowledge_max_tokens": _thousands(knowledge.max_total_chars // CHARS_PER_TOKEN),
        "knowledge_percent": min(100, round(100 * used / knowledge.max_total_chars)) if knowledge.max_total_chars else 0,
        "document_accept": ",".join(knowledge.supported_extensions),
        "max_document_mb": knowledge.max_document_bytes // (1024 * 1024),
    }


def _ai_context(
    persona: AiPersona,
    available: bool,
    model_groups: list[dict],
    catalog_error: str = "",
    message: str = "",
    message_class: str = "",
) -> dict:
    return {
        "active": "ai",
        "message": message,
        "message_class": message_class,
        "persona": persona,
        "available": available,
        "model_groups": model_groups,
        "catalog_error": catalog_error,
        "max_length": MAX_SYSTEM_INSTRUCTION_LENGTH,
        "max_context_length": MAX_CONTEXT_LENGTH,
    }


def _squad_context(
    personas: list[SquadPersona],
    members: Mapping[int, SquadMember],
    model_groups: dict[int, list[dict]],
    catalog_error: str = "",
    message: str = "",
    message_class: str = "",
    saved_slot: int | None = None,
) -> dict:
    return {
        "active": "squad",
        "message": message,
        "message_class": message_class,
        "saved_slot": saved_slot,
        "catalog_error": catalog_error,
        "limit": MAX_MESSAGES_PER_BOT_PER_TOPIC,
        "max_personality_length": MAX_PERSONALITY_LENGTH,
        "max_secret_goal_length": MAX_SECRET_GOAL_LENGTH,
        "bots": [
            {"persona": persona, "member": members.get(persona.slot), "model_groups": model_groups[persona.slot]}
            for persona in personas
        ],
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
    model_catalog: ModelCatalog | None,
    knowledge: KnowledgeBase,
    squad_personas: SquadPersonaService,
    squad_members: Callable[[], Mapping[int, SquadMember]],
    squad_model_catalog: ModelCatalog | None,
    renderer: ViewRenderer | None = None,
) -> web.Application:
    sessions = SessionStore()
    renderer = renderer or ViewRenderer()
    # client_max_size: el panel de IA admite subir varios documentos de la
    # base de conocimiento de una vez.
    app = web.Application(
        middlewares=[_auth_middleware(user_service, sessions)],
        client_max_size=knowledge.max_document_bytes * 3 + 1024 * 1024,
    )

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
    async def available_models() -> tuple[tuple[ModelInfo, ...], str]:
        if model_catalog is None:
            return (), ""
        try:
            return await model_catalog.list_models(), ""
        except ModelCatalogError as exc:
            return (), f"No se pudo obtener la lista de modelos ({exc}). Solo se muestra el guardado."

    async def render_ai(request: web.Request, persona: AiPersona, message: str = "",
                        message_class: str = "") -> web.Response:
        models, catalog_error = await available_models()
        return html_response("admin/ai.html", **_ai_context(
            persona, answer_mention is not None, _model_groups(models, persona.model), catalog_error,
            message, message_class,
        ), **_knowledge_context(knowledge), **_user_context(request))

    async def ai_get(request: web.Request) -> web.Response:
        return await render_ai(request, ai_personas.current)

    async def ai_post(request: web.Request) -> web.Response:
        data = await request.post()
        try:
            persona = AiPersona(
                system_instruction=str(data.get("system_instruction", "")).replace("\r\n", "\n").strip(),
                model=str(data.get("model", "")).strip(),
                enabled=data.get("enabled") == "on",
                context=str(data.get("context", "")).replace("\r\n", "\n").strip(),
            )
        except ValueError as exc:
            return await render_ai(request, ai_personas.current, str(exc), "err")

        # El desplegable solo ofrece modelos listados (o el ya guardado); se
        # revalida aqui por si el POST llega manipulado o la lista cambio.
        models, _ = await available_models()
        if models and persona.model != ai_personas.current.model and persona.model not in {m.id for m in models}:
            return await render_ai(request, ai_personas.current, f"Modelo no disponible: {persona.model}.", "err")

        await ai_personas.change(persona)
        return await render_ai(request, persona, "Identidad y contexto guardados.", "ok")

    # ---------------- admin: base de conocimiento ----------------
    def document_id(request: web.Request) -> int:
        try:
            return int(request.match_info["document_id"])
        except ValueError:
            raise web.HTTPNotFound()

    async def documents_upload(request: web.Request) -> web.Response:
        data = await request.post()
        uploads = [f for f in data.getall("documents", []) if isinstance(f, web.FileField) and f.filename]
        if not uploads:
            return await render_ai(request, ai_personas.current, "Elige al menos un fichero.", "err")
        saved, disabled, errors = [], [], []
        for upload in uploads:
            try:
                document = await knowledge.add(
                    upload.filename, upload.content_type or "application/octet-stream", upload.file.read()
                )
            except KnowledgeBaseError as exc:
                errors.append(str(exc))
                continue
            (saved if document.enabled else disabled).append(document.filename)
        parts = []
        if saved:
            parts.append("Subido: " + ", ".join(saved) + ".")
        if disabled:
            parts.append(
                "Guardado pero DESACTIVADO por superar el límite de tokens por pregunta: "
                + ", ".join(disabled) + "."
            )
        parts.extend(errors)
        return await render_ai(request, ai_personas.current, " ".join(parts), "err" if errors or disabled else "ok")

    async def documents_toggle(request: web.Request) -> web.Response:
        data = await request.post()
        enabled = data.get("enabled") == "1"
        try:
            await knowledge.set_enabled(document_id(request), enabled)
        except KnowledgeBaseError as exc:
            return await render_ai(request, ai_personas.current, str(exc), "err")
        raise web.HTTPFound("/admin/ai#documents")

    async def documents_delete(request: web.Request) -> web.Response:
        try:
            await knowledge.delete(document_id(request))
        except KnowledgeBaseError as exc:
            return await render_ai(request, ai_personas.current, str(exc), "err")
        raise web.HTTPFound("/admin/ai#documents")

    async def documents_download(request: web.Request) -> web.Response:
        original = await knowledge.original(document_id(request))
        if original is None:
            raise web.HTTPNotFound()
        filename, _, content = original
        # Siempre como descarga y sin interpretar el tipo: el fichero lo subio
        # un usuario y no debe ejecutarse en el origen del panel.
        return web.Response(body=content, headers={
            "Content-Type": "application/octet-stream",
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
            "X-Content-Type-Options": "nosniff",
        })

    # ---------------- admin: bots del topic ----------------
    async def squad_models() -> tuple[tuple[ModelInfo, ...], str]:
        if squad_model_catalog is None:
            return (), ""
        try:
            return await squad_model_catalog.list_models(), ""
        except ModelCatalogError as exc:
            return (), f"No se pudo obtener la lista de modelos ({exc}). Solo se muestra el guardado."

    async def render_squad(request: web.Request, message: str = "", message_class: str = "",
                           saved_slot: int | None = None) -> web.Response:
        models, catalog_error = await squad_models()
        personas = squad_personas.all()
        groups = {p.slot: _model_groups(models, p.model) for p in personas}
        return html_response("admin/squad.html", **_squad_context(
            personas, squad_members(), groups, catalog_error, message, message_class, saved_slot,
        ), **_user_context(request))

    async def squad_get(request: web.Request) -> web.Response:
        return await render_squad(request)

    async def squad_post(request: web.Request) -> web.Response:
        data = await request.post()
        try:
            persona = SquadPersona(
                slot=int(str(data.get("slot", ""))),
                personality=str(data.get("personality", "")).replace("\r\n", "\n").strip(),
                secret_goal=str(data.get("secret_goal", "")).replace("\r\n", "\n").strip(),
                model=str(data.get("model", "")).strip(),
                enabled=data.get("enabled") == "on",
            )
        except ValueError as exc:
            return await render_squad(request, str(exc), "err")

        current = squad_personas.get(persona.slot)
        models, _ = await squad_models()
        if models and persona.model != current.model and persona.model not in {m.id for m in models}:
            return await render_squad(request, f"Modelo no disponible: {persona.model}.", "err", persona.slot)

        await squad_personas.change(persona)
        return await render_squad(request, f"Bot {persona.slot} guardado.", "ok", persona.slot)

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
    app.router.add_post("/admin/ai/documents", documents_upload)
    app.router.add_post("/admin/ai/documents/{document_id}/toggle", documents_toggle)
    app.router.add_post("/admin/ai/documents/{document_id}/delete", documents_delete)
    app.router.add_get("/admin/ai/documents/{document_id}/download", documents_download)
    app.router.add_get("/admin/squad", squad_get)
    app.router.add_post("/admin/squad", squad_post)
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