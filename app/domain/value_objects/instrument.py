from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Market = Literal["us", "ru", "fx", "crypto"]
Category = Literal["us_stock", "us_etf", "ru_stock", "fx", "crypto"]
Currency = Literal["$", "₽"]


@dataclass(frozen=True, slots=True)
class Instrument:
    """Un activo cotizable (acción, ETF o par de divisas) a vigilar."""

    symbol: str
    label: str
    market: Market
    category: Category
    currency: Currency
