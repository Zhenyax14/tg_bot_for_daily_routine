"""Puerto de salida para obtener el instante actual.

Existe para que los casos de uso no dependan del reloj del sistema y sean
deterministas en tests, por el mismo motivo por el que `Notifier` es un puerto.
"""
from __future__ import annotations

from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime:
        """Instante actual como datetime 'aware' en UTC."""
        ...