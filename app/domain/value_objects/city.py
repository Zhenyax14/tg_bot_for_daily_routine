"""Value object que representa una ciudad y su zona horaria IANA.

La conversion de un instante UTC a la hora local de la ciudad -incluido el
cambio de invierno/verano- se delega en `zoneinfo`, que lee la base IANA.
Aqui no se codifica ningun offset a mano: la clave IANA es la unica fuente
de verdad del horario de verano.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True)
class City:
    """Ciudad con su zona horaria. Inmutable y validada en construccion:
    una `City` con zona invalida no puede existir."""

    name: str
    timezone_key: str  # clave IANA, p. ej. "Europe/Madrid"

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("El nombre de la ciudad no puede estar vacio")
        try:
            ZoneInfo(self.timezone_key)  # fuerza la resolucion de la zona
        except ZoneInfoNotFoundError as exc:
            raise ValueError(
                f"Zona horaria IANA desconocida: {self.timezone_key!r}"
            ) from exc

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone_key)  # ZoneInfo cachea; es barato

    def local_time(self, instant: datetime) -> datetime:
        """Convierte un instante (aware) a la hora local de la ciudad.
        El offset correcto -invierno o verano- lo aplica `zoneinfo` segun la
        fecha del instante. Rechaza datetimes naive para evitar ambiguedad."""
        if instant.tzinfo is None:
            raise ValueError("El instante debe ser 'aware' (con tzinfo)")
        return instant.astimezone(self.zone)