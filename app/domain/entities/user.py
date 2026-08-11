"""Entidad: usuario del panel/bot. `password_hash` es SIEMPRE el resultado de
un hash irreversible (bcrypt); el dominio nunca ve ni maneja la contrasena en
claro -- eso ocurre en la capa de aplicacion, a traves del puerto
PasswordHasher.
"""
from __future__ import annotations

from dataclasses import dataclass

from domain.value_objects.user_role import UserRole


@dataclass(frozen=True)
class User:
    id: int | None  # None: usuario aun no persistido
    name: str
    password_hash: str
    role: UserRole
    avatar: str | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("El nombre de usuario no puede estar vacio")
        if not self.password_hash:
            raise ValueError("El usuario necesita un password_hash")