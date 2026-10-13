"""Value object: identidad del asistente de IA (instrucciones de sistema +
modelo + interruptor). Es lo que se "entrena" desde el panel y se guarda en
la BBDD; el adaptador del modelo de lenguaje la recibe tal cual."""
from __future__ import annotations

import re
from dataclasses import dataclass

DEFAULT_AI_MODEL = "gemini-3.1-flash-lite"
MAX_SYSTEM_INSTRUCTION_LENGTH = 20_000

_MODEL_PATTERN = re.compile(r"^[a-z0-9][a-z0-9.\-]{0,79}$")


@dataclass(frozen=True)
class AiPersona:
    system_instruction: str = ""
    model: str = DEFAULT_AI_MODEL
    enabled: bool = True

    def __post_init__(self) -> None:
        if not _MODEL_PATTERN.match(self.model):
            raise ValueError(f"Nombre de modelo invalido: {self.model!r}")
        if len(self.system_instruction) > MAX_SYSTEM_INSTRUCTION_LENGTH:
            raise ValueError(
                f"Las instrucciones superan {MAX_SYSTEM_INSTRUCTION_LENGTH} caracteres"
            )
