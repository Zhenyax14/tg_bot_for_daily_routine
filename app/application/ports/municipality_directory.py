"""Puerto de salida: busca municipios espanoles por nombre (o fragmento)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from domain.value_objects.municipality import Municipality


@dataclass(frozen=True)
class MunicipalitySearchResult:
    municipality: Municipality
    province: str


class MunicipalityDirectory(Protocol):
    async def search(self, query: str) -> tuple[MunicipalitySearchResult, ...]: ...