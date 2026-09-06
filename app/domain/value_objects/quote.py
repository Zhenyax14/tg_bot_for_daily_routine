from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Quote:
    """Precio observado de un instrumento en un instante dado."""

    symbol: str
    price: float
    at: datetime

    def __post_init__(self) -> None:
        if self.price <= 0:
            raise ValueError(f"price debe ser positivo, recibido {self.price!r}")
