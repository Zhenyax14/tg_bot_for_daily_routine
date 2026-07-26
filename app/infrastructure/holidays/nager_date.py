"""Adaptador de HolidayProvider sobre Nager.Date (sin API key; cubre ES y RU).

    GET https://date.nager.at/api/v3/PublicHolidays/{year}/{countryCode}

Para un job una vez al dia, se crea un cliente por peticion (sin ciclo de vida
que gestionar). Se puede inyectar un cliente para tests.
"""
from __future__ import annotations

from datetime import date

import httpx

from domain.value_objects.holiday import Holiday

_BASE_URL = "https://date.nager.at/api/v3"


class NagerDateHolidayProvider:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

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
        return tuple(
            Holiday(
                day=date.fromisoformat(item["date"]),
                name=item["name"],
                local_name=item.get("localName") or item["name"],
                country=item["countryCode"],
            )
            for item in payload
        )