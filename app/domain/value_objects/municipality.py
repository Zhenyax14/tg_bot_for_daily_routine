"""Value object: municipio espanol identificado por su codigo INE (5 digitos).

`name` es informativo y NO participa en la igualdad: dos Municipality con el
mismo INE son el mismo municipio aunque uno traiga nombre y el otro no.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Municipality:
    ine: str
    name: str | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        if not (self.ine.isdigit() and len(self.ine) == 5):
            raise ValueError(
                f"Codigo INE de municipio invalido: {self.ine!r} (deben ser 5 digitos)"
            )