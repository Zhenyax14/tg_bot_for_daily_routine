"""Panel de administracion (aiohttp) con login real (usuario + contrasena) y
sesion por cookie, respaldado en la tabla `users` (contrasenas con bcrypt).
Solo usuarios con role == "admin" pueden entrar. Dentro, el usuario busca su
municipio por NOMBRE (no necesita saber que existe un codigo INE).

Las vistas viven como ficheros .html en resources/views/ (Jinja2), y el CSS/JS
personalizable en resources/static/. Este modulo solo orquesta: construye el
contexto de cada pagina y delega el renderizado en ViewRenderer.
"""
from __future__ import annotations

from pathlib import Path

from aiohttp import web

from application.ports.municipality_directory import MunicipalityDirectory
from application.services.location_service import LocationService
from application.services.user_service import UserService
from domain.value_objects.municipality import Municipality
from infrastructure.web.session_store import SessionStore
from infrastructure.web.view_renderer import ViewRenderer

_MAX_RESULTS_SHOWN = 20
_SESSION_COOKIE = "session"
_SESSION_MAX_AGE = 8 * 60 * 60  # 8 horas
_ADMIN_ROLE = "admin"
_PUBLIC_PATHS = {"/login", "/logout", "/health"}

# app/infrastructure/web/admin_server.py -> parents[2] = app/
_STATIC_DIR = Path(__file__).resolve().parents[2] / "resources" / "static"


def _location_context(location: LocationService, message: str = "", message_class: str = "") -> dict:
    m = location.current
    return {
        "message": message,
        "message_class": message_class,
        "current_ine": m.ine,
        "current_name": m.name,
    }


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
    renderer: ViewRenderer | None = None,
) -> web.Application:
    sessions = SessionStore()
    renderer = renderer or ViewRenderer()
    app = web.Application(middlewares=[_auth_middleware(user_service, sessions)])

    def html_response(template: str, **context) -> web.Response:
        return web.Response(text=renderer.render(template, **context), content_type="text/html")

    async def login_get(request: web.Request) -> web.Response:
        token = request.cookies.get(_SESSION_COOKIE)
        username = sessions.username_for(token) if token else None
        if username is not None:
            raise web.HTTPFound("/")
        return html_response("login.html")

    async def login_post(request: web.Request) -> web.Response:
        data = await request.post()
        name = str(data.get("name", "")).strip()
        password = str(data.get("password", ""))

        user = await user_service.authenticate(name, password)
        if user is None:
            return html_response("login.html", error="Usuario o contraseña incorrectos.")
        if user.role.value != _ADMIN_ROLE:
            return html_response("login.html", error="Este usuario no tiene permiso de administrador.")

        token = sessions.create(user.name)
        response = web.HTTPFound("/")
        response.set_cookie(_SESSION_COOKIE, token, max_age=_SESSION_MAX_AGE, httponly=True, samesite="Lax")
        raise response

    async def logout_post(request: web.Request) -> web.Response:
        token = request.cookies.get(_SESSION_COOKIE)
        if token:
            sessions.destroy(token)
        response = web.HTTPFound("/login")
        response.del_cookie(_SESSION_COOKIE)
        raise response

    async def index(request: web.Request) -> web.Response:
        return html_response("location.html", **_location_context(location))

    async def set_location(request: web.Request) -> web.Response:
        data = await request.post()
        query = str(data.get("nombre", "")).strip()
        if len(query) < 2:
            return html_response(
                "location.html", **_location_context(location, "Escribe al menos 2 letras.", "err")
            )

        results = await municipality_directory.search(query)
        if not results:
            return html_response(
                "location.html",
                **_location_context(location, f'No se encontró ningún municipio llamado "{query}".', "err"),
            )
        if len(results) == 1:
            await location.change(results[0].municipality)
            name = results[0].municipality.name
            return html_response(
                "location.html", **_location_context(location, f"Guardado: {name}.", "ok")
            )
        if len(results) > _MAX_RESULTS_SHOWN:
            return html_response(
                "location.html",
                **_location_context(
                    location,
                    f'Demasiados resultados ({len(results)}) para "{query}". Escribe un nombre más específico.',
                    "err",
                ),
            )
        return html_response("candidates.html", query=query, results=results)

    async def confirm_location(request: web.Request) -> web.Response:
        data = await request.post()
        ine = str(data.get("ine", "")).strip()
        name = str(data.get("name", "")).strip() or None
        try:
            municipality = Municipality(ine=ine, name=name)
        except ValueError:
            return html_response(
                "location.html", **_location_context(location, "Selección inválida.", "err")
            )
        await location.change(municipality)
        return html_response(
            "location.html", **_location_context(location, f"Guardado: {name or ine}.", "ok")
        )

    async def health(request: web.Request) -> web.Response:
        return web.Response(text="ok")

    app.router.add_get("/login", login_get)
    app.router.add_post("/login", login_post)
    app.router.add_post("/logout", logout_post)
    app.router.add_get("/", index)
    app.router.add_post("/location", set_location)
    app.router.add_post("/location/confirm", confirm_location)
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