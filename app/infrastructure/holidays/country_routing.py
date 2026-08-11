"""Provider compuesto: enruta cada pais a su adaptador concreto.

Mantiene el puerto HolidayProvider intacto para los casos de uso; solo cambia
que detras de "ES" y "RU" hay fuentes distintas.
"""
from __future__ import annotations

from application.ports.holiday_provider import HolidayProvider
from domain.value_objects.holiday import Holiday


class CountryRoutingHolidayProvider:
    def __init__(self, providers: dict[str, HolidayProvider]) -> None:
        self._providers = dict(providers)

    async def holidays(self, country: str, year: int) -> tuple[Holiday, ...]:
        provider = self._providers.get(country)
        if provider is None:
            return ()
        return await provider.holidays(country, year)