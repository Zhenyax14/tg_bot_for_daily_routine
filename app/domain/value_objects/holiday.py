"""Value object de un festivo publico."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Holiday:
    day: date
    name: str        # nombre en ingles (canonico de la API)
    local_name: str  # nombre en idioma local, para felicitar
    country: str     # codigo ISO-3166 alpha-2: "ES", "RU"

    def __post_init__(self) -> None:
        if len(self.country) != 2:
            raise ValueError(f"Codigo de pais invalido: {self.country!r}")
        if not self.local_name.strip():
            raise ValueError("El festivo necesita un nombre local")