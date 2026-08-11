"""Servicio de aplicacion: cachea la localidad en memoria (lectura sincrona en el
hot path) respaldada en el repositorio async. Se carga al arrancar con load()."""
from __future__ import annotations

from domain.repositories.location_repository import LocationRepository
from domain.value_objects.municipality import Municipality


class LocationService:
    def __init__(self, repository: LocationRepository, default: Municipality) -> None:
        self._repository = repository
        self._default = default
        self._current = default

    async def load(self) -> None:
        self._current = await self._repository.load() or self._default

    @property
    def current(self) -> Municipality:
        return self._current

    async def change(self, municipality: Municipality) -> None:
        await self._repository.save(municipality)
        self._current = municipality