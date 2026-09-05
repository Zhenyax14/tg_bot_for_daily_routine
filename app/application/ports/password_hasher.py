"""Puerto de salida: hash irreversible de contrasenas. La implementacion
concreta (bcrypt, argon2...) vive en infraestructura."""
from __future__ import annotations

from typing import Protocol


class PasswordHasher(Protocol):
    def hash(self, plain_password: str) -> str: ...
    def verify(self, plain_password: str, password_hash: str) -> bool: ...