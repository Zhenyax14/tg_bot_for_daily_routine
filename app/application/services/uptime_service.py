"""Servicio de aplicacion: mide cuanto lleva el proceso del bot en marcha.

Guarda el instante de arranque (marcado una vez al iniciar) y ofrece el tiempo
transcurrido. No depende de detalles de infraestructura: recibe un proveedor
de "ahora" (monotonic) por constructor, para poder testearlo con un reloj
falso.
"""
from __future__ import annotations

from collections.abc import Callable


class UptimeService:
    def __init__(self, monotonic: Callable[[], float]) -> None:
        self._monotonic = monotonic
        self._started_at: float | None = None

    def mark_started(self) -> None:
        self._started_at = self._monotonic()

    def uptime_seconds(self) -> int:
        if self._started_at is None:
            return 0
        return int(self._monotonic() - self._started_at)

    def uptime_human(self) -> str:
        total = self.uptime_seconds()
        days, rem = divmod(total, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, _ = divmod(rem, 60)
        parts = []
        if days:
            parts.append(f"{days}d")
        if hours or days:
            parts.append(f"{hours}h")
        parts.append(f"{minutes}m")
        return " ".join(parts)