"""Value object: rol de un usuario. Texto libre y normalizado (sin espacios,
en minusculas) en vez de un enum cerrado: los roles concretos (admin,
moderador, etc.) los definira el feature que los use, no este VO.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UserRole:
    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip().lower()
        if not normalized:
            raise ValueError("El rol no puede estar vacio")
        if len(normalized) > 50:
            raise ValueError("El rol es demasiado largo (maximo 50 caracteres)")
        object.__setattr__(self, "value", normalized)