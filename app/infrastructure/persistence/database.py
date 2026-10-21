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

CREATE TABLE IF NOT EXISTS ai_persona (
    id                 boolean PRIMARY KEY DEFAULT true CHECK (id),
    system_instruction text NOT NULL DEFAULT '',
    model              text NOT NULL,
    enabled            boolean NOT NULL DEFAULT true,
    updated_at         timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE ai_persona ADD COLUMN IF NOT EXISTS context text NOT NULL DEFAULT '';

-- Base de conocimiento del asistente: el texto se extrae una vez al subir
-- el fichero; el original se guarda para poder descargarlo desde el panel.
CREATE TABLE IF NOT EXISTS ai_documents (
    id           serial PRIMARY KEY,
    filename     text NOT NULL,
    content_type text NOT NULL,
    content      bytea NOT NULL,
    text_content text NOT NULL,
    size_bytes   integer NOT NULL,
    enabled      boolean NOT NULL DEFAULT true,
    created_at   timestamptz NOT NULL DEFAULT now()
);

-- Bots del topic multi-bot: una fila por bot (slot 1..3).
CREATE TABLE IF NOT EXISTS squad_personas (
    slot        smallint PRIMARY KEY CHECK (slot BETWEEN 1 AND 3),
    personality text NOT NULL DEFAULT '',
    secret_goal text NOT NULL DEFAULT '',
    model       text NOT NULL,
    enabled     boolean NOT NULL DEFAULT true,
    updated_at  timestamptz NOT NULL DEFAULT now()
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