"""Interfaz del repositorio de localidad (dominio). Async: la implementacion
concreta habla con Postgres via asyncpg."""
from __future__ import annotations

from typing import Protocol

from domain.value_objects.municipality import Municipality


class LocationRepository(Protocol):
    async def load(self) -> Municipality | None: ...
    async def save(self, municipality: Municipality) -> None: ...