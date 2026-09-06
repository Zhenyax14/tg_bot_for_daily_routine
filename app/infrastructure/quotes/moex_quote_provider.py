from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterable

import httpx

from domain.value_objects.instrument import Instrument
from domain.value_objects.quote import Quote

logger = logging.getLogger(__name__)

_SHARES_URL = (
    "https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities/{secid}.json"
)
_FX_URL = (
    "https://iss.moex.com/iss/engines/currency/markets/selt/boards/CETS/securities/{secid}.json"
)
_PARAMS = {"iss.only": "marketdata", "iss.meta": "off"}


class MoexQuoteProvider:
    """Cotizaciones RU (acciones TQBR) y FX (CETS) desde MOEX ISS, sin clave."""

    def __init__(self, timeout: float = 10.0) -> None:
        self._timeout = timeout

    async def fetch(self, instruments: Iterable[Instrument]) -> list[Quote]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            quotes: list[Quote] = []
            for instrument in instruments:
                quote = await self._fetch_one(client, instrument)
                if quote is not None:
                    quotes.append(quote)
            return quotes

    async def _fetch_one(self, client: httpx.AsyncClient, instrument: Instrument) -> Quote | None:
        url = (_FX_URL if instrument.market == "fx" else _SHARES_URL).format(secid=instrument.symbol)
        try:
            response = await client.get(url, params=_PARAMS)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("MOEX: fallo al pedir %s: %s", instrument.symbol, exc)
            return None

        marketdata = response.json().get("marketdata", {})
        columns = marketdata.get("columns", [])
        rows = marketdata.get("data", [])
        if not rows or "LAST" not in columns:
            return None

        last = rows[0][columns.index("LAST")]
        if last is None:
            logger.info("MOEX: %s sin precio (mercado cerrado)", instrument.symbol)
            return None

        return Quote(symbol=instrument.symbol, price=float(last), at=datetime.now(timezone.utc))
