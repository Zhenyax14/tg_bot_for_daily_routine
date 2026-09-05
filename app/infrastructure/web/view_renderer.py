"""Adaptador de renderizado: envuelve Jinja2 para cargar plantillas desde
resources/views/ (fuera del codigo Python, editable en HTML/CSS/JS puro, al
estilo Laravel). Presentacion pura -- no importa nada de dominio ni de
aplicacion.

Jinja2 escapa automaticamente (autoescape) todo lo que se interpola con
{{ }}, asi que ya no hace falta llamar a html.escape() a mano en cada vista.
"""
from __future__ import annotations

from pathlib import Path

import jinja2

# app/infrastructure/web/view_renderer.py -> parents[2] = app/
_DEFAULT_VIEWS_DIR = Path(__file__).resolve().parents[2] / "resources" / "views"


class ViewRenderer:
    def __init__(self, views_dir: Path = _DEFAULT_VIEWS_DIR) -> None:
        self._env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(views_dir)),
            autoescape=jinja2.select_autoescape(["html"]),
        )

    def render(self, template_name: str, **context) -> str:
        return self._env.get_template(template_name).render(**context)