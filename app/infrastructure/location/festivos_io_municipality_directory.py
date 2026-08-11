"""Adaptador de MunicipalityDirectory sobre el listado oficial de municipios
de festivos.io (fuente: diccionario de municipios del INE). No anade ninguna
API externa nueva: reutiliza el mismo dominio que ya se usa para festivos.

    GET https://festivos.io/v1/ref/municipios.json

La lista (~8100 municipios) se descarga una vez y se cachea en memoria durante
la vida del proceso: el diccionario del INE solo se actualiza una vez al anio.
"""
from __future__ import annotations

import httpx

from application.ports.municipality_directory import MunicipalitySearchResult
from domain.value_objects.municipality import Municipality

_URL = "https://festivos.io/v1/ref/municipios.json"


class FestivosIoMunicipalityDirectory:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client
        self._cache: tuple[MunicipalitySearchResult, ...] | None = None

    async def _all(self) -> tuple[MunicipalitySearchResult, ...]:
        if self._cache is not None:
            return self._cache
        if self._client is not None:
            resp = await self._client.get(_URL)
        else:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(_URL)
        resp.raise_for_status()
        payload = resp.json()
        self._cache = tuple(
            MunicipalitySearchResult(
                municipality=Municipality(ine=m["ine"], name=m["name"]),
                province=m.get("province_name", ""),
            )
            for m in payload.get("municipalities", ())
        )
        return self._cache

    async def search(self, query: str) -> tuple[MunicipalitySearchResult, ...]:
        needle = query.strip().casefold()
        if not needle:
            return ()
        haystack = await self._all()
        return tuple(r for r in haystack if needle in r.municipality.name.casefold())