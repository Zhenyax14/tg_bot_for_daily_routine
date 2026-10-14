"""Servicio de aplicacion: cachea en memoria la identidad del asistente de IA
(lectura sincrona en cada mencion) respaldada en el repositorio async. Se
carga al arrancar con load(), mismo patron que LocationService."""
from __future__ import annotations

from domain.repositories.ai_persona_repository import AiPersonaRepository
from domain.value_objects.ai_persona import AiPersona


class AiPersonaService:
    def __init__(self, repository: AiPersonaRepository, default: AiPersona | None = None) -> None:
        self._repository = repository
        self._default = default or AiPersona()
        self._current = self._default

    async def load(self) -> None:
        self._current = await self._repository.load() or self._default

    @property
    def current(self) -> AiPersona:
        return self._current

    async def change(self, persona: AiPersona) -> None:
        await self._repository.save(persona)
        self._current = persona
