"""Value object: imagen adjunta a un turno de conversacion (foto o archivo de
imagen de Telegram) que se envia al modelo de lenguaje para que la analice."""
from __future__ import annotations

from dataclasses import dataclass, field

# Formatos de imagen que acepta Gemini como inline_data.
SUPPORTED_IMAGE_TYPES = frozenset({"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"})
# Una peticion a Gemini admite ~20 MB en total y las imagenes viajan en
# base64 (+33 %): 14 MB de imagen cruda es el maximo que cabe en una sola
# peticion. Es a la vez el limite por imagen y el presupuesto por peticion.
MAX_IMAGE_BYTES = 14 * 1024 * 1024
MAX_REQUEST_IMAGE_BYTES = MAX_IMAGE_BYTES


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
