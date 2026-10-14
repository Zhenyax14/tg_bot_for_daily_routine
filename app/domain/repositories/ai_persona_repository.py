"""Interfaz del repositorio de la identidad del asistente de IA (dominio)."""
from __future__ import annotations

from typing import Protocol

from domain.value_objects.ai_persona import AiPersona


class AiPersonaRepository(Protocol):
    async def load(self) -> AiPersona | None: ...
    async def save(self, persona: AiPersona) -> None: ...
