"""Adaptador de renderizado: envuelve Jinja2 para cargar plantillas desde
resources/views/ (fuera del codigo Python, editable en HTML/CSS/JS puro, al
estilo Laravel). Presentacion pura -- no importa nada de dominio ni de
aplicacion.

Jinja2 escapa automaticamente (autoescape) todo lo que se interpola con
{{ }}, asi que ya no hace falta llamar a html.escape() a mano en cada vista.

`asset('css/app.css')` en una vista devuelve `/static/css/app.css?v=<mtime>`:
al cambiar el fichero cambia la URL y el navegador no sirve una copia vieja
de su cache tras un despliegue (antes hacia falta Ctrl+Shift+R).
"""
from __future__ import annotations

from pathlib import Path

import jinja2

# app/infrastructure/web/view_renderer.py -> parents[2] = app/
_DEFAULT_VIEWS_DIR = Path(__file__).resolve().parents[2] / "resources" / "views"
_DEFAULT_STATIC_DIR = Path(__file__).resolve().parents[2] / "resources" / "static"


class ViewRenderer:
    def __init__(self, views_dir: Path = _DEFAULT_VIEWS_DIR, static_dir: Path = _DEFAULT_STATIC_DIR) -> None:
        self._static_dir = static_dir
        self._env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(views_dir)),
            autoescape=jinja2.select_autoescape(["html"]),
        )
        self._env.globals["asset"] = self._asset_url

    def _asset_url(self, path: str) -> str:
        try:
            version = int((self._static_dir / path).stat().st_mtime)
        except OSError:
            return f"/static/{path}"
        return f"/static/{path}?v={version}"

    def render(self, template_name: str, **context) -> str:
        return self._env.get_template(template_name).render(**context)