from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterable

import httpx

from domain.value_objects.instrument import Instrument
from domain.value_objects.quote import Quote

logger = logging.getLogger(__name__)

_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
_HEADERS = {"User-Agent": "Mozilla/5.0"}


class YahooFinanceQuoteProvider:
    """Cotizaciones US/ETF desde el endpoint público (sin clave) de Yahoo Finance.

    Reemplaza a Stooq: su CSV público quedó detrás de un reto JS anti-bot
    (proof-of-work) y dejó de servir datos a peticiones HTTP simples.
    """

    def __init__(self, timeout: float = 10.0) -> None:
        self._timeout = timeout

    async def fetch(self, instruments: Iterable[Instrument]) -> list[Quote]:
        async with httpx.AsyncClient(timeout=self._timeout, headers=_HEADERS) as client:
            quotes: list[Quote] = []
            for instrument in instruments:
                quote = await self._fetch_one(client, instrument)
                if quote is not None:
                    quotes.append(quote)
            return quotes

    async def _fetch_one(self, client: httpx.AsyncClient, instrument: Instrument) -> Quote | None:
        try:
            response = await client.get(_URL.format(symbol=instrument.symbol))
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Yahoo Finance: fallo al pedir %s: %s", instrument.symbol, exc)
            return None

        result = response.json().get("chart", {}).get("result")
        if not result:
            logger.info("Yahoo Finance: %s sin datos", instrument.symbol)
            return None

        price = result[0].get("meta", {}).get("regularMarketPrice")
        if price is None:
            logger.info("Yahoo Finance: %s sin precio", instrument.symbol)
            return None

        return Quote(symbol=instrument.symbol, price=float(price), at=datetime.now(timezone.utc))
