"""Value object: un turno de conversacion con el asistente de IA. `user` es
lo que escribe una persona (texto + imagenes opcionales); `model` es lo que
respondio el propio bot (solo texto)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from domain.value_objects.image_attachment import ImageAttachment

ChatRole = Literal["user", "model"]


@dataclass(frozen=True)
class ChatTurn:
    role: ChatRole
    text: str
    images: tuple[ImageAttachment, ...] = ()

    def __post_init__(self) -> None:
        if self.role not in ("user", "model"):
            raise ValueError(f"Rol de turno invalido: {self.role!r}")
        if self.role == "model" and self.images:
            raise ValueError("Un turno del modelo no lleva imagenes")

    @property
    def image_bytes(self) -> int:
        return sum(len(image.data) for image in self.images)
