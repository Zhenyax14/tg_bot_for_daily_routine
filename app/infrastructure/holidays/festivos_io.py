"""Adaptador de HolidayProvider sobre festivos.io (Espana, por municipio INE).

Recibe un *supplier* del codigo INE (no un valor fijo), para que el cambio de
localidad desde el panel web tenga efecto sin reiniciar. Datos del BOE y
boletines autonomicos, CC BY 4.0.

    GET https://festivos.io/v1/{year}/municipio/{ine}.json
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import date

import httpx

from domain.value_objects.holiday import Holiday

_BASE_URL = "https://festivos.io/v1"


class FestivosIoHolidayProvider:
    def __init__(
        self,
        municipio_supplier: Callable[[], str],
        client: httpx.AsyncClient | None = None,
        levels: Iterable[str] | None = None,
    ) -> None:
        self._municipio_supplier = municipio_supplier
        self._client = client
        self._levels = set(levels) if levels is not None else None  # None = todos

    async def holidays(self, country: str, year: int) -> tuple[Holiday, ...]:
        municipio = self._municipio_supplier()
        url = f"{_BASE_URL}/{year}/municipio/{municipio}.json"
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
        for h in payload.get("holidays", ()):
            if self._levels is not None and h.get("level") not in self._levels:
                continue
            names = h.get("name") or {}
            name = names.get("es") or next(iter(names.values()), "")
            result.append(
                Holiday(day=date.fromisoformat(h["date"]), name=name, local_name=name, country="ES")
            )
        return tuple(result)