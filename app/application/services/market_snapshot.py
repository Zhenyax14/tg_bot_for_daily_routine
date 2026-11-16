"""Servicio de aplicacion: foto del mercado vigilado en este momento.

Obtiene las cotizaciones de los instrumentos habilitados en el panel y las
acompana del primer precio visto hoy (`day_opens`, compartido con las alertas)
para dar la variacion del dia. La usan la revision periodica del robo-advisor
y sus respuestas a preguntas en el hilo de alertas.
"""
from __future__ import annotations

from application.ports.quote_provider import QuoteProvider
from application.services.instrument_settings_service import InstrumentSettingsService
from application.services.reference_prices import ReferencePrices
from domain.value_objects.market_moves import MarketQuote


class MarketSnapshot:
    def __init__(
        self,
        instrument_settings: InstrumentSettingsService,
        provider: QuoteProvider,
        day_opens: ReferencePrices,
    ) -> None:
        self._instrument_settings = instrument_settings
        self._provider = provider
        self._day_opens = day_opens

    async def take(self) -> tuple[MarketQuote, ...]:
        instruments = self._instrument_settings.enabled_instruments()
        quotes = await self._provider.fetch(instruments)
        by_symbol = {instrument.symbol: instrument for instrument in instruments}
        market: list[MarketQuote] = []
        for quote in quotes:
            instrument = by_symbol.get(quote.symbol)
            if instrument is None:
                continue
            day_open = self._day_opens.reference_for(quote.symbol)
            if day_open is None:
                day_open = quote.price
                self._day_opens.set_reference(quote.symbol, day_open)
            market.append(MarketQuote(instrument, quote.price, day_open))
        return tuple(market)
