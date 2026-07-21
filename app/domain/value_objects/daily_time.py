from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DailyTime:
    """Hora del día, validada. Value object: inmutable y sin identidad."""

    hour: int
    minute: int

    def __post_init__(self) -> None:
        if not 0 <= self.hour <= 23:
            raise ValueError(f"Hora fuera de rango: {self.hour}")
        if not 0 <= self.minute <= 59:
            raise ValueError(f"Minuto fuera de rango: {self.minute}")

    @classmethod
    def parse(cls, value: str) -> DailyTime:
        hour, _, minute = value.partition(":")
        try:
            return cls(int(hour), int(minute))
        except ValueError as exc:
            raise ValueError(f"Hora inválida {value!r}, se esperaba HH:MM") from exc

    def __str__(self) -> str:
        return f"{self.hour:02d}:{self.minute:02d}"