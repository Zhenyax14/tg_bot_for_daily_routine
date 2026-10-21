"""Value object: identidad de uno de los bots del topic multi-bot (slot 1..3).
Ademas de la personalidad lleva una meta secreta, que el bot persigue de
forma sutil y nunca revela. Se edita desde el panel y se guarda en la BBDD."""
from __future__ import annotations

import re
from dataclasses import dataclass

from domain.value_objects.ai_persona import DEFAULT_AI_MODEL

SQUAD_SLOTS = (1, 2, 3)
MAX_PERSONALITY_LENGTH = 20_000
MAX_SECRET_GOAL_LENGTH = 5_000
MAX_SPONTANEOUS_PER_DAY = 48

_MODEL_PATTERN = re.compile(r"^[a-z0-9][a-z0-9.\-]{0,79}$")


@dataclass(frozen=True)
class SquadPersona:
    slot: int
    personality: str = ""
    secret_goal: str = ""
    model: str = DEFAULT_AI_MODEL
    enabled: bool = True
    # Media de mensajes al dia que publica por iniciativa propia (0 = nunca).
    spontaneous_per_day: int = 0

    def __post_init__(self) -> None:
        if self.slot not in SQUAD_SLOTS:
            raise ValueError(f"Slot de bot invalido: {self.slot!r}")
        if not _MODEL_PATTERN.match(self.model):
            raise ValueError(f"Nombre de modelo invalido: {self.model!r}")
        if len(self.personality) > MAX_PERSONALITY_LENGTH:
            raise ValueError(f"La personalidad supera {MAX_PERSONALITY_LENGTH} caracteres")
        if len(self.secret_goal) > MAX_SECRET_GOAL_LENGTH:
            raise ValueError(f"La meta secreta supera {MAX_SECRET_GOAL_LENGTH} caracteres")
        if not 0 <= self.spontaneous_per_day <= MAX_SPONTANEOUS_PER_DAY:
            raise ValueError(f"Los mensajes espontaneos al dia van de 0 a {MAX_SPONTANEOUS_PER_DAY}")
