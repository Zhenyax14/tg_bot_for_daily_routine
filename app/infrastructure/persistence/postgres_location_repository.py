"""Adaptador de LocationRepository sobre PostgreSQL (asyncpg). Fila unica."""
from __future__ import annotations

from domain.value_objects.municipality import Municipality
from infrastructure.persistence.database import Database


class PostgresLocationRepository:
    def __init__(self, database: Database) -> None:
        self._db = database

    async def load(self) -> Municipality | None:
        row = await self._db.pool.fetchrow("SELECT ine FROM location WHERE id = true")
        return Municipality(row["ine"]) if row else None

    async def save(self, municipality: Municipality) -> None:
        await self._db.pool.execute(
            "INSERT INTO location (id, ine) VALUES (true, $1) "
            "ON CONFLICT (id) DO UPDATE SET ine = EXCLUDED.ine",
            municipality.ine,
        )