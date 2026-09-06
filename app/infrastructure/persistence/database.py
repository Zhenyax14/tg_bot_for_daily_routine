"""Conexion a PostgreSQL (asyncpg): pool + creacion/actualizacion idempotente
del esquema."""
from __future__ import annotations

import asyncpg

_SCHEMA = """
CREATE TABLE IF NOT EXISTS location (
    id  boolean PRIMARY KEY DEFAULT true CHECK (id),
    ine text NOT NULL
);
ALTER TABLE location ADD COLUMN IF NOT EXISTS nombre text;

CREATE TABLE IF NOT EXISTS users (
    id            serial PRIMARY KEY,
    name          text NOT NULL UNIQUE,
    password_hash text NOT NULL,
    role          text NOT NULL,
    avatar        text
);

CREATE TABLE IF NOT EXISTS instrument_disabled (
    symbol text PRIMARY KEY
);
"""


class Database:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=5)

    async def init_schema(self) -> None:
        await self.pool.execute(_SCHEMA)

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    @property
    def pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("Database.connect() no ha sido llamado todavia")
        return self._pool