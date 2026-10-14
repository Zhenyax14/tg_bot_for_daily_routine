from __future__ import annotations

from typing import Protocol, Sequence

from domain.value_objects.chat_turn import ChatTurn


class LanguageModelError(Exception):
    """El proveedor del modelo no pudo generar una respuesta."""


class LanguageModel(Protocol):
    async def generate(self, model: str, system_instruction: str, conversation: Sequence[ChatTurn]) -> str: ...
