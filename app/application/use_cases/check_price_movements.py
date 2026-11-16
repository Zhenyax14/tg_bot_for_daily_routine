from __future__ import annotations

import logging
from typing import Awaitable, Callable

from application.ports.quote_provider import QuoteProvider
from application.services.instrument_settings_service import InstrumentSettingsService
from application.services.reference_prices import ReferencePrices
from domain.services.price_movement_policy import Movement, PriceMovementPolicy
from domain.value_objects.instrument import Instrument
from domain.value_objects.market_moves import MarketMoves, MarketQuote, PriceAlert

AlertCallback = Callable[[Instrument, Movement], Awaitable[None]]
MovesListener = Callable[[MarketMoves], Awaitable[None]]

logger = logging.getLogger(__name__)


class CheckPriceMovements:
    """Un ciclo de vigilancia: obtiene cotizaciones y dispara alertas de
    movimientos significativos, encadenando la referencia (trail ±5%). Los
    instrumentos habilitados se releen en cada ciclo, así que un cambio hecho
    desde el panel de administración se aplica sin reiniciar el bot.

    Si el ciclo dispara alguna alerta, después de enviarlas todas se avisa a
    `on_moves` con un único evento (alertas + foto del mercado), para que una
    caída generalizada produzca un solo análisis y no uno por instrumento."""

    def __init__(
        self,
        instrument_settings: InstrumentSettingsService,
        provider: QuoteProvider,
        references: ReferencePrices,
        policy: PriceMovementPolicy,
        alert: AlertCallback,
        day_opens: ReferencePrices | None = None,
        on_moves: MovesListener | None = None,
    ) -> None:
        self._instrument_settings = instrument_settings
        self._provider = provider
        self._references = references
        self._policy = policy
        self._alert = alert
        # Primer precio visto hoy por símbolo (no se encadena como el trail):
        # da la variación del día que acompaña al evento.
        self._day_opens = day_opens if day_opens is not None else ReferencePrices(references.today)
        self._on_moves = on_moves

    async def execute(self) -> None:
        instruments = self._instrument_settings.enabled_instruments()
        quotes = await self._provider.fetch(instruments)
        by_symbol = {instrument.symbol: instrument for instrument in instruments}
        market: list[MarketQuote] = []
        alerts: list[PriceAlert] = []
        for quote in quotes:
            instrument = by_symbol.get(quote.symbol)
            if instrument is None:
                continue

            day_open = self._day_opens.reference_for(quote.symbol)
            if day_open is None:
                day_open = quote.price
                self._day_opens.set_reference(quote.symbol, day_open)
            market_quote = MarketQuote(instrument, quote.price, day_open)
            market.append(market_quote)

            reference = self._references.reference_for(quote.symbol)
            if reference is None:
                self._references.set_reference(quote.symbol, quote.price)
                continue

            if not self._policy.is_significant(reference, quote.price):
                continue

            movement = self._policy.movement(reference, quote.price)
            self._references.set_reference(quote.symbol, quote.price)
            alerts.append(PriceAlert(market_quote, movement))
            try:
                await self._alert(instrument, movement)
            except Exception:
                logger.exception("Fallo al enviar la alerta de %s", quote.symbol)

        if alerts and self._on_moves is not None:
            try:
                await self._on_moves(MarketMoves(tuple(alerts), tuple(market)))
            except Exception:
                logger.exception("Fallo al procesar el evento de movimientos de mercado")
