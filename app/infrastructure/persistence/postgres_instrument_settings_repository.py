"""Adaptador de InstrumentSettingsRepository sobre PostgreSQL (asyncpg).

Solo se guardan los símbolos deshabilitados: la ausencia de fila significa
"habilitado" (el valor por defecto), así que añadir un instrumento nuevo al
catálogo no requiere ninguna migración de datos.
"""
from __future__ import annotations

from infrastructure.persistence.database import Database


class PostgresInstrumentSettingsRepository:
    def __init__(self, database: Database) -> None:
        self._db = database

    async def load_disabled_symbols(self) -> set[str]:
        rows = await self._db.pool.fetch("SELECT symbol FROM instrument_disabled")
        return {row["symbol"] for row in rows}

    async def set_enabled(self, symbol: str, enabled: bool) -> None:
        if enabled:
            await self._db.pool.execute("DELETE FROM instrument_disabled WHERE symbol = $1", symbol)
        else:
            await self._db.pool.execute(
                "INSERT INTO instrument_disabled (symbol) VALUES ($1) ON CONFLICT (symbol) DO NOTHING",
                symbol,
            )
