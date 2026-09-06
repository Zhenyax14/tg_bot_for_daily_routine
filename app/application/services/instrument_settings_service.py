"""Servicio de aplicacion: cachea en memoria que instrumentos del catalogo
estan habilitados para disparar avisos (lectura sincrona en el hot path del
job de 5 minutos), respaldado por el repositorio async. Se carga con load()."""
from __future__ import annotations

from domain.repositories.instrument_settings_repository import InstrumentSettingsRepository
from domain.value_objects.instrument import Instrument


class InstrumentSettingsService:
    def __init__(self, repository: InstrumentSettingsRepository, catalog: list[Instrument]) -> None:
        self._repository = repository
        self._catalog = catalog
        self._disabled: set[str] = set()

    async def load(self) -> None:
        self._disabled = await self._repository.load_disabled_symbols()

    def enabled_instruments(self) -> list[Instrument]:
        return [i for i in self._catalog if i.symbol not in self._disabled]

    def is_enabled(self, symbol: str) -> bool:
        return symbol not in self._disabled

    async def set_enabled(self, symbol: str, enabled: bool) -> None:
        await self._repository.set_enabled(symbol, enabled)
        if enabled:
            self._disabled.discard(symbol)
        else:
            self._disabled.add(symbol)

    async def apply_enabled_symbols(self, enabled_symbols: set[str]) -> None:
        """Aplica un envío completo del formulario: todo lo que no está en
        `enabled_symbols` queda deshabilitado."""
        for instrument in self._catalog:
            await self.set_enabled(instrument.symbol, instrument.symbol in enabled_symbols)
