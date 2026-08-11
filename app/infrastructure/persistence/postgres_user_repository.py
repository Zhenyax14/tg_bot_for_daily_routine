"""Adaptador de UserRepository sobre PostgreSQL (asyncpg)."""
from __future__ import annotations

from domain.entities.user import User
from domain.value_objects.user_role import UserRole
from infrastructure.persistence.database import Database


def _row_to_user(row) -> User:
    return User(
        id=row["id"],
        name=row["name"],
        password_hash=row["password_hash"],
        role=UserRole(row["role"]),
        avatar=row["avatar"],
    )


class PostgresUserRepository:
    def __init__(self, database: Database) -> None:
        self._db = database

    async def add(self, user: User) -> User:
        row = await self._db.pool.fetchrow(
            "INSERT INTO users (name, password_hash, role, avatar) "
            "VALUES ($1, $2, $3, $4) RETURNING id, name, password_hash, role, avatar",
            user.name, user.password_hash, user.role.value, user.avatar,
        )
        return _row_to_user(row)

    async def get_by_name(self, name: str) -> User | None:
        row = await self._db.pool.fetchrow(
            "SELECT id, name, password_hash, role, avatar FROM users WHERE name = $1", name
        )
        return _row_to_user(row) if row else None

    async def list_all(self) -> tuple[User, ...]:
        rows = await self._db.pool.fetch(
            "SELECT id, name, password_hash, role, avatar FROM users ORDER BY id"
        )
        return tuple(_row_to_user(r) for r in rows)

    async def update(self, user: User) -> None:
        await self._db.pool.execute(
            "UPDATE users SET name = $1, password_hash = $2, role = $3, avatar = $4 WHERE id = $5",
            user.name, user.password_hash, user.role.value, user.avatar, user.id,
        )

    async def delete(self, user_id: int) -> None:
        await self._db.pool.execute("DELETE FROM users WHERE id = $1", user_id)

    async def count(self) -> int:
        return await self._db.pool.fetchval("SELECT count(*) FROM users")