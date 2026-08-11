"""Servicio de aplicacion: crea usuarios (hasheando la contrasena) y autentica
por nombre + contrasena en claro contra el hash almacenado."""
from __future__ import annotations

from application.ports.password_hasher import PasswordHasher
from domain.entities.user import User
from domain.repositories.user_repository import UserRepository
from domain.value_objects.user_role import UserRole


class UserService:
    def __init__(self, repository: UserRepository, hasher: PasswordHasher) -> None:
        self._repository = repository
        self._hasher = hasher

    async def create(
        self, name: str, plain_password: str, role: UserRole, avatar: str | None = None
    ) -> User:
        password_hash = self._hasher.hash(plain_password)
        user = User(id=None, name=name, password_hash=password_hash, role=role, avatar=avatar)
        return await self._repository.add(user)

    async def authenticate(self, name: str, plain_password: str) -> User | None:
        user = await self._repository.get_by_name(name)
        if user is None:
            return None
        if not self._hasher.verify(plain_password, user.password_hash):
            return None
        return user

    async def get_by_name(self, name: str) -> User | None:
        return await self._repository.get_by_name(name)