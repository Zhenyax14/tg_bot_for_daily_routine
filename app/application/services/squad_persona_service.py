"""Servicio de aplicacion: cachea en memoria las identidades de los bots del
topic (lectura sincrona en cada mensaje), respaldadas en el repositorio
async. Mismo patron que AiPersonaService."""
from __future__ import annotations

from domain.repositories.squad_persona_repository import SquadPersonaRepository
from domain.value_objects.squad_persona import SQUAD_SLOTS, SquadPersona


class SquadPersonaService:
    def __init__(self, repository: SquadPersonaRepository) -> None:
        self._repository = repository
        self._personas = {slot: SquadPersona(slot) for slot in SQUAD_SLOTS}

    async def load(self) -> None:
        for persona in await self._repository.load_all():
            self._personas[persona.slot] = persona

    def get(self, slot: int) -> SquadPersona:
        return self._personas[slot]

    def all(self) -> list[SquadPersona]:
        return [self._personas[slot] for slot in SQUAD_SLOTS]

    async def change(self, persona: SquadPersona) -> None:
        await self._repository.save(persona)
        self._personas[persona.slot] = persona
