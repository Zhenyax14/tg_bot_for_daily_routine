from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Movement:
    """Un movimiento de precio entre una referencia y el precio actual."""

    reference: float
    current: float

    @property
    def percent(self) -> float:
        return (self.current - self.reference) / self.reference * 100


@dataclass(frozen=True, slots=True)
class PriceMovementPolicy:
    """Umbral que decide si un movimiento de precio es significativo."""

    threshold_percent: float = 5.0

    def movement(self, reference: float, current: float) -> Movement:
        return Movement(reference, current)

    def is_significant(self, reference: float, current: float) -> bool:
        return abs(self.movement(reference, current).percent) >= self.threshold_percent
