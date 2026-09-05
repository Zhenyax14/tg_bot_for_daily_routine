"""Adaptador de HolidayProvider sobre Nager.Date (sin API key).

Por defecto filtra a festivos NACIONALES y de tipo "Public" (dia no laborable en
todo el pais), descartando regionales y observancias.

    GET https://date.nager.at/api/v3/PublicHolidays/{year}/{countryCode}
"""
from __future__ import annotations

from datetime import date

import httpx

from domain.value_objects.holiday import Holiday

_BASE_URL = "https://date.nager.at/api/v3"


class NagerDateHolidayProvider:
    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        national_only: bool = True,
        public_only: bool = True,
    ) -> None:
        self._client = client
        self._national_only = national_only
        self._public_only = public_only

    async def holidays(self, country: str, year: int) -> tuple[Holiday, ...]:
        url = f"{_BASE_URL}/PublicHolidays/{year}/{country}"
        if self._client is not None:
            resp = await self._client.get(url)
            resp.raise_for_status()
            payload = resp.json()
        else:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                payload = resp.json()

        result: list[Holiday] = []
        for item in payload:
            if self._national_only and item.get("global") is not True:
                continue
            if self._public_only and "Public" not in (item.get("types") or []):
                continue
            result.append(
                Holiday(
                    day=date.fromisoformat(item["date"]),
                    name=item["name"],
                    local_name=item.get("localName") or item["name"],
                    country=item["countryCode"],
                )
            )
        return tuple(result)