"""Interfaz del repositorio de ajustes de instrumentos (dominio). Guarda,
por símbolo, si está habilitado para disparar avisos de precio."""
from __future__ import annotations

from typing import Protocol


class InstrumentSettingsRepository(Protocol):
    async def load_disabled_symbols(self) -> set[str]: ...
    async def set_enabled(self, symbol: str, enabled: bool) -> None: ...
