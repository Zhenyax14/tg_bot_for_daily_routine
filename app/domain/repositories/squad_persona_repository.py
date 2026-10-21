"""Interfaz del repositorio de identidades de los bots del topic (dominio)."""
from __future__ import annotations

from typing import Protocol

from domain.value_objects.squad_persona import SquadPersona


class SquadPersonaRepository(Protocol):
    async def load_all(self) -> list[SquadPersona]: ...
    async def save(self, persona: SquadPersona) -> None: ...
