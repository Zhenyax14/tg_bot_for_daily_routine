"""Value object: un turno de conversacion con el asistente de IA. `user` es
lo que escribe una persona; `model` es lo que respondio el propio bot."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ChatRole = Literal["user", "model"]


@dataclass(frozen=True)
class ChatTurn:
    role: ChatRole
    text: str

    def __post_init__(self) -> None:
        if self.role not in ("user", "model"):
            raise ValueError(f"Rol de turno invalido: {self.role!r}")
