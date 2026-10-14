"""Caso de uso: responder a una mencion del bot con el modelo de lenguaje,
usando la identidad, el contexto y los documentos configurados en el panel.

Antes de llamar al modelo ajusta las imagenes al presupuesto por peticion:
si el hilo acumula demasiadas (albumes, seguimientos con varios graficos),
se quitan las mas antiguas y se conservan siempre las mas recientes.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Sequence

from application.ports.language_model import LanguageModel
from application.services.ai_persona_service import AiPersonaService
from application.services.knowledge_base import KnowledgeBase
from application.services.system_prompt import build_system_instruction
from domain.value_objects.ai_persona import AiPersona
from domain.value_objects.chat_turn import ChatTurn
from domain.value_objects.image_attachment import MAX_REQUEST_IMAGE_BYTES

DROPPED_IMAGES_NOTE = "[изображения из этого сообщения больше недоступны]"


class AnswerMention:
    def __init__(
        self,
        personas: AiPersonaService,
        language_model: LanguageModel,
        knowledge: KnowledgeBase,
        max_image_bytes: int = MAX_REQUEST_IMAGE_BYTES,
    ) -> None:
        self._personas = personas
        self._language_model = language_model
        self._knowledge = knowledge
        self._max_image_bytes = max_image_bytes

    @property
    def enabled(self) -> bool:
        return self._personas.current.enabled

    async def execute(self, conversation: Sequence[ChatTurn], persona: AiPersona | None = None) -> str:
        """`conversation` acaba en el turno del usuario a responder. `persona`
        permite probar una identidad aun no guardada (panel)."""
        persona = persona or self._personas.current
        system_instruction = build_system_instruction(persona, self._knowledge.enabled_documents())
        fitted = fit_images(conversation, self._max_image_bytes)
        return await self._language_model.generate(persona.model, system_instruction, fitted)


def fit_images(conversation: Sequence[ChatTurn], max_bytes: int) -> list[ChatTurn]:
    """Recorre de lo mas reciente a lo mas antiguo conservando imagenes
    mientras quepan en `max_bytes`; los turnos que pierden imagenes llevan una
    nota para que el modelo sepa que existian."""
    budget = max_bytes
    fitted: list[ChatTurn] = []
    for turn in reversed(conversation):
        if not turn.images:
            fitted.append(turn)
            continue
        kept = []
        for image in reversed(turn.images):
            if len(image.data) <= budget:
                kept.append(image)
                budget -= len(image.data)
        kept.reverse()
        if len(kept) == len(turn.images):
            fitted.append(turn)
        else:
            text = f"{turn.text}\n{DROPPED_IMAGES_NOTE}" if turn.text else DROPPED_IMAGES_NOTE
            fitted.append(replace(turn, text=text, images=tuple(kept)))
    fitted.reverse()
    return fitted
