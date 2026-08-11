"""Almacen de sesiones en memoria: token aleatorio -> nombre de usuario.
Vale para un panel de un solo proceso; las sesiones se pierden al reiniciar
(el usuario simplemente vuelve a iniciar sesion, sin mas consecuencia).
"""
from __future__ import annotations

import secrets


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, str] = {}

    def create(self, username: str) -> str:
        token = secrets.token_urlsafe(32)
        self._sessions[token] = username
        return token

    def username_for(self, token: str) -> str | None:
        return self._sessions.get(token)

    def destroy(self, token: str) -> None:
        self._sessions.pop(token, None)