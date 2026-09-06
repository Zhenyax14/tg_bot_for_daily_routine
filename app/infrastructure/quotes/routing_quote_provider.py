from __future__ import annotations

import logging
from collections import defaultdict
from typing import Iterable

from application.ports.quote_provider import QuoteProvider
from domain.value_objects.instrument import Instrument
from domain.value_objects.quote import Quote

logger = logging.getLogger(__name__)


class RoutingQuoteProvider:
    """Reparte instrumentos por mercado al proveedor correspondiente; el fallo
    de un mercado no impide obtener cotizaciones de los demás."""

    def __init__(self, by_market: dict[str, QuoteProvider]) -> None:
        self._by_market = by_market

    async def fetch(self, instruments: Iterable[Instrument]) -> list[Quote]:
        grouped: dict[str, list[Instrument]] = defaultdict(list)
        for instrument in instruments:
            grouped[instrument.market].append(instrument)

        quotes: list[Quote] = []
        for market, market_instruments in grouped.items():
            provider = self._by_market.get(market)
            if provider is None:
                logger.warning("Sin proveedor de cotizaciones para el mercado %r", market)
                continue
            try:
                quotes.extend(await provider.fetch(market_instruments))
            except Exception:
                logger.exception("Fallo al obtener cotizaciones del mercado %r", market)
        return quotes
