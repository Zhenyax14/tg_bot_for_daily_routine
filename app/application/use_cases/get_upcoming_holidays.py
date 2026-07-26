"""Caso de uso: festivos en la ventana de los proximos N dias (ES y RU)."""
from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta

from application.ports.clock import Clock
from application.ports.holiday_provider import HolidayProvider
from domain.value_objects.holiday import Holiday

DEFAULT_COUNTRIES: tuple[str, ...] = ("ES", "RU")


class GetUpcomingHolidays:
    def __init__(
        self,
        provider: HolidayProvider,
        clock: Clock,
        days: int = 7,
        countries: Sequence[str] = DEFAULT_COUNTRIES,
    ) -> None:
        self._provider = provider
        self._clock = clock
        self._days = days
        self._countries = tuple(countries)

    async def execute(self) -> tuple[Holiday, ...]:
        today = self._clock.now().date()
        end = today + timedelta(days=self._days)
        years = {today.year, end.year}  # cubre el cruce de anio (finales de diciembre)
        found: list[Holiday] = []
        for country in self._countries:
            for year in years:
                for h in await self._provider.holidays(country, year):
                    if today <= h.day <= end:
                        found.append(h)
        return tuple(sorted(found, key=lambda h: (h.day, h.country)))