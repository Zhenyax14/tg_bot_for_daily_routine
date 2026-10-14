"""Value object: identidad del asistente de IA (instrucciones de sistema +
contexto del grupo + modelo + interruptor). Es lo que se "entrena" desde el
panel y se guarda en la BBDD. Los documentos de la base de conocimiento van
aparte (KnowledgeDocument) y se combinan al construir el prompt."""
from __future__ import annotations

import re
from dataclasses import dataclass

DEFAULT_AI_MODEL = "gemini-3.1-flash-lite"
MAX_SYSTEM_INSTRUCTION_LENGTH = 20_000
MAX_CONTEXT_LENGTH = 50_000

_MODEL_PATTERN = re.compile(r"^[a-z0-9][a-z0-9.\-]{0,79}$")


@dataclass(frozen=True)
class AiPersona:
    system_instruction: str = ""
    model: str = DEFAULT_AI_MODEL
    enabled: bool = True
    context: str = ""

    def __post_init__(self) -> None:
        if not _MODEL_PATTERN.match(self.model):
            raise ValueError(f"Nombre de modelo invalido: {self.model!r}")
        if len(self.system_instruction) > MAX_SYSTEM_INSTRUCTION_LENGTH:
            raise ValueError(
                f"Las instrucciones superan {MAX_SYSTEM_INSTRUCTION_LENGTH} caracteres"
            )
        if len(self.context) > MAX_CONTEXT_LENGTH:
            raise ValueError(f"El contexto supera {MAX_CONTEXT_LENGTH} caracteres")
