"""Caso de uso: hora local actual de un conjunto de ciudades."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from application.ports.clock import Clock
from domain.value_objects.city import City


@dataclass(frozen=True)
class CityTime:
    city: City
    local_time: datetime


class GetWorldTimes:
    def __init__(self, clock: Clock, cities: Sequence[City]) -> None:
        self._clock = clock
        self._cities = tuple(cities)

    def execute(self) -> tuple[CityTime, ...]:
        instant = self._clock.now()
        return tuple(
            CityTime(city, city.local_time(instant)) for city in self._cities
        )