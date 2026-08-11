"""Caso de uso: siembra el primer usuario admin si la tabla de usuarios esta
vacia. No hace nada si ya existe algun usuario -- evita resetear credenciales
en cada reinicio del contenedor.
"""
from __future__ import annotations

from application.services.user_service import UserService
from domain.repositories.user_repository import UserRepository
from domain.value_objects.user_role import UserRole


class BootstrapAdminUser:
    def __init__(self, repository: UserRepository, user_service: UserService) -> None:
        self._repository = repository
        self._user_service = user_service

    async def execute(self, name: str, plain_password: str, role: str) -> None:
        if await self._repository.count() > 0:
            return
        await self._user_service.create(name, plain_password, UserRole(role))