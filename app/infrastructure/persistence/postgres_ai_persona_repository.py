"""Adaptador de AiPersonaRepository sobre PostgreSQL (asyncpg). Fila unica."""
from __future__ import annotations

from domain.value_objects.ai_persona import AiPersona
from infrastructure.persistence.database import Database


class PostgresAiPersonaRepository:
    def __init__(self, database: Database) -> None:
        self._db = database

    async def load(self) -> AiPersona | None:
        row = await self._db.pool.fetchrow(
            "SELECT system_instruction, model, enabled, context FROM ai_persona WHERE id = true"
        )
        if row is None:
            return None
        return AiPersona(
            system_instruction=row["system_instruction"],
            model=row["model"],
            enabled=row["enabled"],
            context=row["context"],
        )

    async def save(self, persona: AiPersona) -> None:
        await self._db.pool.execute(
            "INSERT INTO ai_persona (id, system_instruction, model, enabled, context, updated_at) "
            "VALUES (true, $1, $2, $3, $4, now()) "
            "ON CONFLICT (id) DO UPDATE SET system_instruction = EXCLUDED.system_instruction, "
            "model = EXCLUDED.model, enabled = EXCLUDED.enabled, context = EXCLUDED.context, "
            "updated_at = now()",
            persona.system_instruction, persona.model, persona.enabled, persona.context,
        )
