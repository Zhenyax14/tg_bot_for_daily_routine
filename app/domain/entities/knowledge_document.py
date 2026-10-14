"""Entidad: documento de la base de conocimiento del asistente de IA (p. ej.
la configuracion de los grupos). Solo lleva el texto ya extraido; el fichero
original vive en el repositorio y se pide aparte para descargarlo."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

CHARS_PER_TOKEN = 4  # estimacion habitual para texto en idiomas europeos


@dataclass(frozen=True)
class KnowledgeDocument:
    id: int
    filename: str
    content_type: str
    text: str = field(repr=False)
    size_bytes: int
    enabled: bool
    created_at: datetime

    @property
    def chars(self) -> int:
        return len(self.text)

    @property
    def approx_tokens(self) -> int:
        return self.chars // CHARS_PER_TOKEN
