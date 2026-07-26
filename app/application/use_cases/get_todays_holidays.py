"""Caso de uso: festivos de hoy en los paises vigilados (ES, RU)."""
from __future__ import annotations

from collections.abc import Sequence

from application.ports.clock import Clock
from application.ports.holiday_provider import HolidayProvider
from domain.value_objects.holiday import Holiday

DEFAULT_COUNTRIES: tuple[str, ...] = ("ES", "RU")


class GetTodaysHolidays:
    def __init__(
        self,
        provider: HolidayProvider,
        clock: Clock,
        countries: Sequence[str] = DEFAULT_COUNTRIES,
    ) -> None:
        self._provider = provider
        self._clock = clock
        self._countries = tuple(countries)

    async def execute(self) -> tuple[Holiday, ...]:
        today = self._clock.now().date()
        found: list[Holiday] = []
        for country in self._countries:
            for holiday in await self._provider.holidays(country, today.year):
                if holiday.day == today:
                    found.append(holiday)
        return tuple(found)