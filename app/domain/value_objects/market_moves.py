"""Value objects del evento "movimientos de mercado detectados".

Un ciclo de vigilancia de precios que dispara al menos una alerta produce un
`MarketMoves`: las alertas del ciclo + la foto de todo el mercado vigilado en
ese momento (precio actual y variacion desde el primer precio del dia). Es lo
que recibe quien quiera reaccionar al evento (p. ej. el analisis por IA).
"""
from __future__ import annotations

from dataclasses import dataclass

from domain.services.price_movement_policy import Movement
from domain.value_objects.instrument import Instrument


@dataclass(frozen=True, slots=True)
class MarketQuote:
    """Precio actual de un instrumento y el primero que se vio hoy."""

    instrument: Instrument
    price: float
    day_open: float

    @property
    def day_change_percent(self) -> float:
        return Movement(self.day_open, self.price).percent


@dataclass(frozen=True, slots=True)
class PriceAlert:
    """Una alerta disparada: el salto respecto a la referencia del trail."""

    quote: MarketQuote
    movement: Movement

    @property
    def instrument(self) -> Instrument:
        return self.quote.instrument


@dataclass(frozen=True, slots=True)
class MarketMoves:
    alerts: tuple[PriceAlert, ...]
    market: tuple[MarketQuote, ...]
