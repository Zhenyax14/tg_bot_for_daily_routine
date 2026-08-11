"""Panel de administracion (aiohttp). El usuario escribe el NOMBRE de su
municipio -- no necesita saber que existe un codigo INE. Se busca en el
directorio de municipios (festivos.io); si hay una unica coincidencia se
guarda directamente, si hay varias se pide elegir.
"""
from __future__ import annotations

import html

import base64
from aiohttp import web

from application.ports.municipality_directory import MunicipalityDirectory
from application.services.location_service import LocationService
from domain.value_objects.municipality import Municipality

_MAX_RESULTS_SHOWN = 20

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
</style></head><body>
<h1>Configuración del bot</h1>
{body}
</body></html>"""

_FORM = """{msg}
<form method="post" action="/location">
 <label for="nombre">Nombre del municipio (España)</label>
 <input id="nombre" name="nombre" placeholder="Benidorm" required>
 <div><button type="submit">Buscar</button></div>
</form>
<p class="cur">{current_line}</p>"""


def _current_line(location: LocationService) -> str:
    m = location.current
    if m.name:
        return f"Localidad actual: <strong>{html.escape(m.name)}</strong> (INE {m.ine})"
    return f"Localidad actual: INE <strong>{m.ine}</strong>"


def _render_form(location: LocationService, msg: str = "") -> web.Response:
    body = _FORM.format(msg=msg, current_line=_current_line(location))
    return web.Response(text=_PAGE.format(body=body), content_type="text/html")


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
    return web.Response(text=_PAGE.format(body=body), content_type="text/html")


def _auth_middleware(user: str, password: str):
    @web.middleware
    async def middleware(request: web.Request, handler):
        if request.path == "/health":
            return await handler(request)
        header = request.headers.get("Authorization", "")
        if header.startswith("Basic "):
            try:
                got_user, _, got_pwd = base64.b64decode(header[6:]).decode().partition(":")
                if got_user == user and got_pwd == password:
                    return await handler(request)
            except Exception:
                pass
        return web.Response(status=401, text="401 Unauthorized",
                            headers={"WWW-Authenticate": 'Basic realm="bot admin"'})
    return middleware


def build_admin_app(
    location: LocationService,
    municipality_directory: MunicipalityDirectory,
    user: str,
    password: str,
) -> web.Application:
    app = web.Application(middlewares=[_auth_middleware(user, password)])

    async def index(request):
        return _render_form(location)

    async def set_location(request):
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

    async def confirm_location(request):
        data = await request.post()
        ine = str(data.get("ine", "")).strip()
        name = str(data.get("name", "")).strip() or None
        try:
            municipality = Municipality(ine=ine, name=name)
        except ValueError:
            return _render_form(location, '<div class="msg err">Selección inválida.</div>')
        await location.change(municipality)
        return _render_form(location, f'<div class="msg ok">Guardado: {html.escape(name or ine)}.</div>')

    async def health(request):
        return web.Response(text="ok")

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