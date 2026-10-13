"""Value object: imagen adjunta a un turno de conversacion (foto o archivo de
imagen de Telegram) que se envia al modelo de lenguaje para que la analice."""
from __future__ import annotations

from dataclasses import dataclass, field

# Formatos de imagen que acepta Gemini como inline_data.
SUPPORTED_IMAGE_TYPES = frozenset({"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"})
MAX_IMAGE_BYTES = 15 * 1024 * 1024  # la peticion inline a Gemini admite ~20 MB en total


class ImageTooLarge(ValueError):
    pass


class UnsupportedImageType(ValueError):
    pass


@dataclass(frozen=True)
class ImageAttachment:
    mime_type: str
    data: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if self.mime_type not in SUPPORTED_IMAGE_TYPES:
            raise UnsupportedImageType(f"Formato de imagen no soportado: {self.mime_type!r}")
        if not self.data:
            raise ValueError("Imagen vacia")
        if len(self.data) > MAX_IMAGE_BYTES:
            raise ImageTooLarge(f"Imagen demasiado grande: {len(self.data)} bytes")
