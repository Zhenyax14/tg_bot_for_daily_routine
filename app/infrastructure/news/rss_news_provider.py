"""Adaptador de NewsProvider sobre feeds RSS de buscadores de noticias
(gratis, sin clave), con respaldo:

1. Google News RSS: `news.google.com/rss/search?q=<consulta> when:1d`.
2. Bing News RSS: `bing.com/news/search?q=<consulta>&format=rss` (filtro de
   ultimas 24 h `qft=interval="7"`), si Google falla.

Google limita por IP (429 tras una rafaga de consultas): tras un 429 se deja
de usar durante `google_cooldown` y se va directo a Bing. Cada consulta se
cachea `cache_ttl` (las revisiones de 30 min y las preguntas repiten las
mismas), con timeout corto y como mucho 3 peticiones a la vez.

Una consulta por instrumento (en ingles para US/cripto, en ruso para MOEX y
divisas) + una de mercado general por cada mercado implicado. Resultado:
titulares de las ultimas ~36 h, sin duplicados, los mas recientes primero.
Una consulta que falla en ambas fuentes se registra y se ignora.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Callable, Sequence

import httpx

from domain.value_objects.instrument import Instrument
from domain.value_objects.news_headline import NewsHeadline

logger = logging.getLogger(__name__)

_GOOGLE_URL = "https://news.google.com/rss/search"
_GOOGLE_EDITIONS = {
    "en": {"hl": "en-US", "gl": "US", "ceid": "US:en"},
    "ru": {"hl": "ru", "gl": "RU", "ceid": "RU:ru"},
}
_BING_URL = "https://www.bing.com/news/search"
_BING_MARKETS = {"en": "en-US", "ru": "ru-RU"}

_MARKET_QUERIES = {"en": "stock market today", "ru": "российский рынок акций Мосбиржа"}
_FX_QUERIES = {
    "USD000UTSTOM": "курс доллара рубль",
    "CNYRUB_TOM": "курс юаня рубль",
    "TRYRUB_TOM": "курс турецкой лиры",
    "KZTRUB_TOM": "курс тенге рубль",
}
_PER_QUERY = 5
_MAX_HEADLINES = 25
_MAX_AGE = timedelta(hours=36)


class _SourceFailed(Exception):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class RssNewsProvider:
    def __init__(
        self,
        timeout: float = 5.0,
        cache_ttl: float = 900.0,
        google_cooldown: float = 900.0,
        transport: httpx.AsyncBaseTransport | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._timeout = timeout
        self._cache_ttl = cache_ttl
        self._google_cooldown = google_cooldown
        self._transport = transport
        self._monotonic = monotonic
        self._google_blocked_until = 0.0
        self._cache: dict[tuple[str, str], tuple[float, list[NewsHeadline]]] = {}
        self._semaphore = asyncio.Semaphore(3)

    async def latest(self, instruments: Sequence[Instrument]) -> list[NewsHeadline]:
        queries = _queries(instruments)
        async with httpx.AsyncClient(
            timeout=self._timeout, transport=self._transport,
            headers={"User-Agent": "Mozilla/5.0"}, follow_redirects=True,
        ) as client:
            results = await asyncio.gather(*(self._search(client, q, lang) for q, lang in queries))

        oldest = datetime.now(timezone.utc) - _MAX_AGE
        seen: set[str] = set()
        headlines: list[NewsHeadline] = []
        for found in results:
            for headline in found:
                key = headline.title.lower()
                if key in seen or (headline.published_at is not None and headline.published_at < oldest):
                    continue
                seen.add(key)
                headlines.append(headline)
        headlines.sort(key=lambda h: h.published_at.timestamp() if h.published_at else 0, reverse=True)
        return headlines[:_MAX_HEADLINES]

    async def _search(self, client: httpx.AsyncClient, query: str, lang: str) -> list[NewsHeadline]:
        key = (query, lang)
        cached = self._cache.get(key)
        if cached is not None and self._monotonic() - cached[0] < self._cache_ttl:
            return cached[1]

        async with self._semaphore:
            found: list[NewsHeadline] | None = None
            if self._monotonic() >= self._google_blocked_until:
                try:
                    found = await self._google(client, query, lang)
                except _SourceFailed as exc:
                    if exc.status == 429:
                        self._google_blocked_until = self._monotonic() + self._google_cooldown
                        logger.warning("Noticias: Google News limita (429); se usa Bing %.0f min",
                                       self._google_cooldown / 60)
                    else:
                        logger.warning("Noticias: Google fallo en %r (%s); se prueba Bing", query, exc)
            if found is None:
                try:
                    found = await self._bing(client, query, lang)
                except _SourceFailed as exc:
                    logger.warning("Noticias: sin titulares para %r (Bing: %s)", query, exc)
                    return []

        found = found[:_PER_QUERY]
        self._cache[key] = (self._monotonic(), found)
        return found

    async def _google(self, client: httpx.AsyncClient, query: str, lang: str) -> list[NewsHeadline]:
        text = await _get(client, _GOOGLE_URL, {"q": f"{query} when:1d", **_GOOGLE_EDITIONS[lang]})
        return _parse(text, strip_source_suffix=True)

    async def _bing(self, client: httpx.AsyncClient, query: str, lang: str) -> list[NewsHeadline]:
        params = {"q": query, "format": "rss", "qft": 'interval="7"', "setmkt": _BING_MARKETS[lang]}
        return _parse(await _get(client, _BING_URL, params), strip_source_suffix=False)


async def _get(client: httpx.AsyncClient, url: str, params: dict) -> str:
    try:
        response = await client.get(url, params=params)
    except httpx.HTTPError as exc:
        raise _SourceFailed(f"red: {exc.__class__.__name__}") from exc
    if response.status_code != 200:
        raise _SourceFailed(f"HTTP {response.status_code}", response.status_code)
    return response.text


def _queries(instruments: Sequence[Instrument]) -> list[tuple[str, str]]:
    queries: list[tuple[str, str]] = []
    markets: set[str] = set()
    for instrument in instruments:
        if instrument.market in ("us", "crypto"):
            markets.add("en")
            label = re.sub(r"\s*\(.*?\)", "", instrument.label).strip()
            suffix = "price" if instrument.market == "crypto" else "stock"
            queries.append((f"{label} {suffix}", "en"))
        elif instrument.market == "fx":
            markets.add("ru")
            queries.append((_FX_QUERIES.get(instrument.symbol, f"курс {instrument.label}"), "ru"))
        else:
            markets.add("ru")
            queries.append((f"{instrument.label} акции", "ru"))
    for lang in sorted(markets or {"en", "ru"}):
        queries.append((_MARKET_QUERIES[lang], lang))
    return list(dict.fromkeys(queries))


def _parse(xml_text: str, strip_source_suffix: bool) -> list[NewsHeadline]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise _SourceFailed(f"RSS invalido: {exc}") from exc
    headlines = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        if not title:
            continue
        # Google: <source>; Bing: <News:Source> con un namespace variable.
        source = (item.findtext("source") or "").strip() or next(
            ((child.text or "").strip() for child in item if child.tag.endswith("}Source")), ""
        )
        # Google pone el medio al final del titulo: "Titular - Medio".
        if strip_source_suffix and source and title.endswith(f" - {source}"):
            title = title[: -len(source) - 3].rstrip()
        try:
            published = parsedate_to_datetime(item.findtext("pubDate") or "")
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            published = None
        headlines.append(NewsHeadline(title, source, published, (item.findtext("link") or "").strip()))
    return headlines
