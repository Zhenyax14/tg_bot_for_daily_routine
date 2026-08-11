"""Value object: municipio espanol identificado por su codigo INE (5 digitos)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Municipality:
    ine: str

    def __post_init__(self) -> None:
        if not (self.ine.isdigit() and len(self.ine) == 5):
            raise ValueError(
                f"Codigo INE de municipio invalido: {self.ine!r} (deben ser 5 digitos)"
            )