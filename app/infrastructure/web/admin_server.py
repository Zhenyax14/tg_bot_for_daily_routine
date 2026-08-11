"""Panel de administracion (aiohttp). Basic Auth por env; change() es async
porque LocationService persiste en Postgres."""
from __future__ import annotations

import base64
import html

from aiohttp import web

from application.services.location_service import LocationService
from domain.value_objects.municipality import Municipality

_PAGE = """<!doctype html>
<html lang="es"><head><meta charset="utf-8"><title>Bot · configuración</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
 body{{font-family:system-ui,-apple-system,sans-serif;max-width:32rem;margin:3rem auto;padding:0 1rem;color:#1a1a1a}}
 h1{{font-size:1.3rem}} label{{display:block;margin:1rem 0 .3rem}}
 input{{font-size:1rem;padding:.45rem;width:8rem}} button{{font-size:1rem;padding:.45rem 1rem;margin-top:1rem;cursor:pointer}}
 .msg{{padding:.5rem .75rem;border-radius:.4rem;margin:1rem 0}} .ok{{background:#e6f4ea}} .err{{background:#fce8e6}}
 .cur{{color:#666;margin-top:1.5rem}}
</style></head><body>
<h1>Configuración del bot</h1>
{msg}
<form method="post" action="/location">
 <label for="ine">Municipio de España — código INE (5 dígitos)</label>
 <input id="ine" name="ine" value="{ine}" pattern="[0-9]{{5}}" inputmode="numeric" required>
 <div><button type="submit">Guardar</button></div>
</form>
<p class="cur">Localidad actual: INE <strong>{ine}</strong></p>
</body></html>"""


def _render(location: LocationService, msg: str = "") -> web.Response:
    return web.Response(
        text=_PAGE.format(ine=html.escape(location.current.ine), msg=msg),
        content_type="text/html",
    )


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


def build_admin_app(location: LocationService, user: str, password: str) -> web.Application:
    app = web.Application(middlewares=[_auth_middleware(user, password)])

    async def index(request):
        return _render(location)

    async def set_location(request):
        data = await request.post()
        raw = str(data.get("ine", "")).strip()
        try:
            await location.change(Municipality(raw))
            return _render(location, '<div class="msg ok">Guardado correctamente.</div>')
        except ValueError:
            return _render(location, '<div class="msg err">Código INE inválido: 5 dígitos.</div>')

    async def health(request):
        return web.Response(text="ok")

    app.router.add_get("/", index)
    app.router.add_post("/location", set_location)
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