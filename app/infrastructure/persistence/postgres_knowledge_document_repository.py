"""Adaptador de KnowledgeDocumentRepository sobre PostgreSQL (asyncpg).
`list_all` no trae el fichero original (bytea): solo hace falta al
descargarlo desde el panel."""
from __future__ import annotations

from domain.entities.knowledge_document import KnowledgeDocument
from infrastructure.persistence.database import Database

_COLUMNS = "id, filename, content_type, text_content, size_bytes, enabled, created_at"


class PostgresKnowledgeDocumentRepository:
    def __init__(self, database: Database) -> None:
        self._db = database

    async def list_all(self) -> list[KnowledgeDocument]:
        rows = await self._db.pool.fetch(f"SELECT {_COLUMNS} FROM ai_documents ORDER BY created_at, id")
        return [_document(row) for row in rows]

    async def add(
        self, filename: str, content_type: str, content: bytes, text: str, enabled: bool
    ) -> KnowledgeDocument:
        row = await self._db.pool.fetchrow(
            "INSERT INTO ai_documents (filename, content_type, content, text_content, size_bytes, enabled) "
            f"VALUES ($1, $2, $3, $4, $5, $6) RETURNING {_COLUMNS}",
            filename, content_type, content, text, len(content), enabled,
        )
        return _document(row)

    async def original(self, document_id: int) -> tuple[str, str, bytes] | None:
        row = await self._db.pool.fetchrow(
            "SELECT filename, content_type, content FROM ai_documents WHERE id = $1", document_id
        )
        return (row["filename"], row["content_type"], bytes(row["content"])) if row else None

    async def set_enabled(self, document_id: int, enabled: bool) -> None:
        await self._db.pool.execute("UPDATE ai_documents SET enabled = $2 WHERE id = $1", document_id, enabled)

    async def delete(self, document_id: int) -> None:
        await self._db.pool.execute("DELETE FROM ai_documents WHERE id = $1", document_id)


def _document(row) -> KnowledgeDocument:
    return KnowledgeDocument(
        id=row["id"],
        filename=row["filename"],
        content_type=row["content_type"],
        text=row["text_content"],
        size_bytes=row["size_bytes"],
        enabled=row["enabled"],
        created_at=row["created_at"],
    )
