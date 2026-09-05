"""Adaptador de PasswordHasher sobre bcrypt: hash con salt aleatorio por
contrasena, computacionalmente costoso de fuerza-bruta y matematicamente
irreversible (no existe "des-hashear", solo volver a probar y comparar)."""
from __future__ import annotations

import bcrypt


class BcryptPasswordHasher:
    def hash(self, plain_password: str) -> str:
        return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    def verify(self, plain_password: str, password_hash: str) -> bool:
        try:
            return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))
        except (ValueError, TypeError):
            return False