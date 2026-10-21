"""Adaptador de SquadPersonaRepository sobre PostgreSQL (asyncpg). Una fila por bot."""
from __future__ import annotations

from domain.value_objects.squad_persona import SquadPersona
from infrastructure.persistence.database import Database


class PostgresSquadPersonaRepository:
    def __init__(self, database: Database) -> None:
        self._db = database

    async def load_all(self) -> list[SquadPersona]:
        rows = await self._db.pool.fetch(
            "SELECT slot, personality, secret_goal, model, enabled, spontaneous_per_day "
            "FROM squad_personas ORDER BY slot"
        )
        return [
            SquadPersona(
                slot=row["slot"],
                personality=row["personality"],
                secret_goal=row["secret_goal"],
                model=row["model"],
                enabled=row["enabled"],
                spontaneous_per_day=row["spontaneous_per_day"],
            )
            for row in rows
        ]

    async def save(self, persona: SquadPersona) -> None:
        await self._db.pool.execute(
            "INSERT INTO squad_personas (slot, personality, secret_goal, model, enabled, spontaneous_per_day, updated_at) "
            "VALUES ($1, $2, $3, $4, $5, $6, now()) "
            "ON CONFLICT (slot) DO UPDATE SET personality = EXCLUDED.personality, "
            "secret_goal = EXCLUDED.secret_goal, model = EXCLUDED.model, enabled = EXCLUDED.enabled, "
            "spontaneous_per_day = EXCLUDED.spontaneous_per_day, updated_at = now()",
            persona.slot, persona.personality, persona.secret_goal, persona.model, persona.enabled,
            persona.spontaneous_per_day,
        )
