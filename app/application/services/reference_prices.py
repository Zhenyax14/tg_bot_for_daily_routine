from __future__ import annotations

from datetime import date
from typing import Callable


class ReferencePrices:
    """Referencia (precio base) por símbolo, reiniciada cada día natural."""

    def __init__(self, today_provider: Callable[[], date]) -> None:
        self._today_provider = today_provider
        self._day: date | None = None
        self._references: dict[str, float] = {}

    def reference_for(self, symbol: str) -> float | None:
        self._reset_if_new_day()
        return self._references.get(symbol)

    def set_reference(self, symbol: str, price: float) -> None:
        self._reset_if_new_day()
        self._references[symbol] = price

    def _reset_if_new_day(self) -> None:
        today = self._today_provider()
        if today != self._day:
            self._day = today
            self._references.clear()
