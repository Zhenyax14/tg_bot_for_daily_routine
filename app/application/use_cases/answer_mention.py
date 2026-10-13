"""Caso de uso: responder a una mencion del bot con el modelo de lenguaje,
usando la identidad configurada en el panel."""
from __future__ import annotations

from typing import Sequence

from application.ports.language_model import LanguageModel
from application.services.ai_persona_service import AiPersonaService
from domain.value_objects.ai_persona import AiPersona
from domain.value_objects.chat_turn import ChatTurn


class AnswerMention:
    def __init__(self, personas: AiPersonaService, language_model: LanguageModel) -> None:
        self._personas = personas
        self._language_model = language_model

    @property
    def enabled(self) -> bool:
        return self._personas.current.enabled

    async def execute(self, conversation: Sequence[ChatTurn], persona: AiPersona | None = None) -> str:
        """`conversation` acaba en el turno del usuario a responder. `persona`
        permite probar una identidad aun no guardada (panel)."""
        return await self._language_model.generate(persona or self._personas.current, conversation)
