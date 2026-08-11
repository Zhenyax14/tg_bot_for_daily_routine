"""Panel de administracion (aiohttp) con login real (usuario + contrasena) y
sesion por cookie, respaldado en la tabla `users` (contrasenas con bcrypt).
Solo usuarios con role == "admin" pueden entrar. Dentro, el usuario busca su
municipio por NOMBRE (no necesita saber que existe un codigo INE).
"""
from __future__ import annotations

import html

from aiohttp import web

from application.ports.municipality_directory import MunicipalityDirectory
from application.services.location_service import LocationService
from application.services.user_service import UserService
from domain.value_objects.municipality import Municipality
from infrastructure.web.session_store import SessionStore

_MAX_RESULTS_SHOWN = 20
_SESSION_COOKIE = "session"
_SESSION_MAX_AGE = 8 * 60 * 60  # 8 horas
_ADMIN_ROLE = "admin"
_PUBLIC_PATHS = {"/login", "/logout", "/health"}

_PAGE = """<!doctype html>
<html lang="es"><head><meta charset="utf-8"><title>Bot · configuración</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
 body{{font-family:system-ui,-apple-system,sans-serif;max-width:32rem;margin:3rem auto;padding:0 1rem;color:#1a1a1a}}
 h1{{font-size:1.3rem}} label{{display:block;margin:1rem 0 .3rem}}
 input{{font-size:1rem;padding:.45rem;width:14rem}} button{{font-size:1rem;padding:.45rem 1rem;margin-top:1rem;cursor:pointer}}
 .msg{{padding:.5rem .75rem;border-radius:.4rem;margin:1rem 0}} .ok{{background:#e6f4ea}} .err{{background:#fce8e6}}
 .cur{{color:#666;margin-top:1.5rem}}
 .candidates{{list-style:none;padding:0}} .candidates li{{margin:.4rem 0}}
 .candidates button{{width:100%;text-align:left;background:#f4f4f4;border:1px solid #ddd}}
 .logout button{{background:none;border:none;color:#666;text-decoration:underline;cursor:pointer;padding:0;margin-top:1.5rem;font-size:.9rem}}
</style></head><body>
<h1>Configuración del bot</h1>
{body}
</body></html>"""

_LOGIN_FORM = """{msg}
<form method="post" action="/login">
 <label for="name">Usuario</label>
 <input id="name" name="name" required autofocus>
 <label for="password">Contraseña</label>
 <input id="password" name="password" type="password" required>
 <div><button type="submit">Entrar</button></div>
</form>"""

_FORM = """{msg}
<form method="post" action="/location">
 <label for="nombre">Nombre del municipio (España)</label>
 <input id="nombre" name="nombre" placeholder="Benidorm" required>
 <div><button type="submit">Buscar</button></div>
</form>
<p class="cur">{current_line}</p>
<form method="post" action="/logout" class="logout"><button type="submit">Cerrar sesión</button></form>"""


def _page(body: str) -> web.Response:
    return web.Response(text=_PAGE.format(body=body), content_type="text/html")


def _render_login(msg: str = "") -> web.Response:
    return _page(_LOGIN_FORM.format(msg=msg))


def _current_line(location: LocationService) -> str:
    m = location.current
    if m.name:
        return f"Localidad actual: <strong>{html.escape(m.name)}</strong> (INE {m.ine})"
    return f"Localidad actual: INE <strong>{m.ine}</strong>"


def _render_form(location: LocationService, msg: str = "") -> web.Response:
    body = _FORM.format(msg=msg, current_line=_current_line(location))
    return _page(body)


def _render_candidates(query: str, results) -> web.Response:
    items = "".join(
        f'<li><form method="post" action="/location/confirm">'
        f'<input type="hidden" name="ine" value="{html.escape(r.municipality.ine)}">'
        f'<input type="hidden" name="name" value="{html.escape(r.municipality.name or "")}">'
        f'<button type="submit">{html.escape(r.municipality.name or r.municipality.ine)} '
        f'({html.escape(r.province)})</button></form></li>'
        for r in results
    )
    body = (
        f'<p>Varios municipios coinciden con "{html.escape(query)}". '
        f"¿Cuál es el tuyo?</p><ul class=\"candidates\">{items}</ul>"
    )
    return _page(body)


def _auth_middleware(user_service: UserService, sessions: SessionStore):
    @web.middleware
    async def middleware(request: web.Request, handler):
        if request.path in _PUBLIC_PATHS:
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
) -> web.Application:
    sessions = SessionStore()
    app = web.Application(middlewares=[_auth_middleware(user_service, sessions)])

    async def login_get(request: web.Request) -> web.Response:
        token = request.cookies.get(_SESSION_COOKIE)
        username = sessions.username_for(token) if token else None
        if username is not None:
            raise web.HTTPFound("/")
        return _render_login()

    async def login_post(request: web.Request) -> web.Response:
        data = await request.post()
        name = str(data.get("name", "")).strip()
        password = str(data.get("password", ""))

        user = await user_service.authenticate(name, password)
        if user is None:
            return _render_login('<div class="msg err">Usuario o contraseña incorrectos.</div>')
        if user.role.value != _ADMIN_ROLE:
            return _render_login('<div class="msg err">Este usuario no tiene permiso de administrador.</div>')

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
        return _render_form(location)

    async def set_location(request: web.Request) -> web.Response:
        data = await request.post()
        query = str(data.get("nombre", "")).strip()
        if len(query) < 2:
            return _render_form(location, '<div class="msg err">Escribe al menos 2 letras.</div>')

        results = await municipality_directory.search(query)
        if not results:
            return _render_form(
                location,
                f'<div class="msg err">No se encontró ningún municipio llamado "{html.escape(query)}".</div>',
            )
        if len(results) == 1:
            await location.change(results[0].municipality)
            name = results[0].municipality.name
            return _render_form(location, f'<div class="msg ok">Guardado: {html.escape(name or "")}.</div>')
        if len(results) > _MAX_RESULTS_SHOWN:
            return _render_form(
                location,
                f'<div class="msg err">Demasiados resultados ({len(results)}) para "{html.escape(query)}". '
                f"Escribe un nombre más específico.</div>",
            )
        return _render_candidates(query, results)

    async def confirm_location(request: web.Request) -> web.Response:
        data = await request.post()
        ine = str(data.get("ine", "")).strip()
        name = str(data.get("name", "")).strip() or None
        try:
            municipality = Municipality(ine=ine, name=name)
        except ValueError:
            return _render_form(location, '<div class="msg err">Selección inválida.</div>')
        await location.change(municipality)
        return _render_form(location, f'<div class="msg ok">Guardado: {html.escape(name or ine)}.</div>')

    async def health(request: web.Request) -> web.Response:
        return web.Response(text="ok")

    app.router.add_get("/login", login_get)
    app.router.add_post("/login", login_post)
    app.router.add_post("/logout", logout_post)
    app.router.add_get("/", index)
    app.router.add_post("/location", set_location)
    app.router.add_post("/location/confirm", confirm_location)
    app.router.add_get("/health", health)
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