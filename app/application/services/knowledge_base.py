"""Servicio de aplicacion: base de conocimiento del asistente de IA.

Cachea en memoria los documentos (con su texto ya extraido) para leerlos en
cada mencion sin ir a la BBDD, igual que AiPersonaService. Todo el texto de
los documentos activos se envia en CADA pregunta, asi que hay un tope total:
un documento que no cabe se guarda desactivado y el panel lo explica.
"""
from __future__ import annotations

from dataclasses import replace

from application.ports.document_text_extractor import DocumentError, DocumentTextExtractor
from domain.entities.knowledge_document import KnowledgeDocument
from domain.repositories.knowledge_document_repository import KnowledgeDocumentRepository

MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
MAX_TOTAL_CHARS = 400_000  # ~100k tokens por pregunta


class KnowledgeBaseError(Exception):
    pass


class KnowledgeBase:
    def __init__(
        self,
        repository: KnowledgeDocumentRepository,
        extractor: DocumentTextExtractor,
        max_total_chars: int = MAX_TOTAL_CHARS,
        max_document_bytes: int = MAX_DOCUMENT_BYTES,
    ) -> None:
        self._repository = repository
        self._extractor = extractor
        self._max_total_chars = max_total_chars
        self._max_document_bytes = max_document_bytes
        self._documents: list[KnowledgeDocument] = []

    async def load(self) -> None:
        self._documents = await self._repository.list_all()

    @property
    def documents(self) -> list[KnowledgeDocument]:
        return list(self._documents)

    @property
    def max_total_chars(self) -> int:
        return self._max_total_chars

    @property
    def max_document_bytes(self) -> int:
        return self._max_document_bytes

    @property
    def supported_extensions(self) -> tuple[str, ...]:
        return self._extractor.supported_extensions

    def enabled_documents(self) -> list[KnowledgeDocument]:
        return [d for d in self._documents if d.enabled]

    def enabled_chars(self) -> int:
        return sum(d.chars for d in self.enabled_documents())

    async def add(self, filename: str, content_type: str, content: bytes) -> KnowledgeDocument:
        """Devuelve el documento guardado; `enabled` es False si no cabia en
        el tope total (se guarda igualmente para activarlo mas tarde)."""
        if not content:
            raise KnowledgeBaseError(f"{filename}: el fichero está vacío.")
        if len(content) > self._max_document_bytes:
            raise KnowledgeBaseError(
                f"{filename}: supera el máximo de {self._max_document_bytes // (1024 * 1024)} MB."
            )
        try:
            text = self._extractor.extract(filename, content).strip()
        except DocumentError as exc:
            raise KnowledgeBaseError(f"{filename}: {exc}") from exc
        if not text:
            raise KnowledgeBaseError(f"{filename}: no contiene texto legible (¿PDF escaneado?).")

        fits = self.enabled_chars() + len(text) <= self._max_total_chars
        document = await self._repository.add(filename, content_type, content, text, fits)
        self._documents.append(document)
        return document

    async def set_enabled(self, document_id: int, enabled: bool) -> None:
        document = self._find(document_id)
        if enabled and not document.enabled and self.enabled_chars() + document.chars > self._max_total_chars:
            limit = f"{self._max_total_chars:,}".replace(",", ".")
            raise KnowledgeBaseError(
                f"{document.filename}: no cabe en el límite de {limit} caracteres por pregunta. "
                "Desactiva otro documento primero."
            )
        await self._repository.set_enabled(document_id, enabled)
        self._replace(document_id, enabled)

    async def delete(self, document_id: int) -> None:
        self._find(document_id)
        await self._repository.delete(document_id)
        self._documents = [d for d in self._documents if d.id != document_id]

    async def original(self, document_id: int) -> tuple[str, str, bytes] | None:
        return await self._repository.original(document_id)

    def _find(self, document_id: int) -> KnowledgeDocument:
        for document in self._documents:
            if document.id == document_id:
                return document
        raise KnowledgeBaseError("El documento no existe.")

    def _replace(self, document_id: int, enabled: bool) -> None:
        self._documents = [replace(d, enabled=enabled) if d.id == document_id else d for d in self._documents]
