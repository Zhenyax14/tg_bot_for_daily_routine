"""Puerto de salida: extrae el texto de un fichero subido (PDF, DOCX, texto)
para meterlo en el prompt del asistente."""
from __future__ import annotations

from typing import Protocol


class DocumentError(Exception):
    """El fichero no se puede usar como documento (formato, vacio, roto)."""


class DocumentTextExtractor(Protocol):
    supported_extensions: tuple[str, ...]

    def extract(self, filename: str, data: bytes) -> str: ...
