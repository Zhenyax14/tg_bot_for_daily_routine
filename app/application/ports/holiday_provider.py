"""Puerto de salida para consultar festivos publicos."""
from __future__ import annotations

from typing import Protocol

from domain.value_objects.holiday import Holiday


class HolidayProvider(Protocol):
    async def holidays(self, country: str, year: int) -> tuple[Holiday, ...]:
        """Festivos publicos de un pais en un anio. El vocabulario de la API
        concreta (Nager.Date, isDayOff, ...) nunca cruza esta frontera."""
        ...