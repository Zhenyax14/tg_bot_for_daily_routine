"""Caso de uso: alguien habla con el robo-advisor (el bot principal) en el
hilo de alertas ("hazme un analisis del mercado ahora").

Toma una foto fresca del mercado vigilado, la anexa a la pregunta y se la
pasa al modelo (`model_name`, el elegido en /admin/ai) con la identidad
estrategica del robo-advisor (no las instrucciones de /admin/ai) y
busqueda web (noticias de hoy). Si la busqueda web falla, se reintenta una
vez sin ella. Si no hay cotizaciones (proveedores caidos) se contesta igual,
solo con la web.
"""
from __future__ import annotations

import logging
from typing import Callable, Sequence

from application.ports.clock import Clock
from application.ports.language_model import LanguageModel, LanguageModelError
from application.services.market_analysis_prompt import build_question_instruction, build_question_request
from application.services.market_snapshot import MarketSnapshot
from domain.value_objects.chat_turn import ChatTurn

logger = logging.getLogger(__name__)


class AnswerAdvisorQuestion:
    def __init__(
        self,
        model: LanguageModel,
        model_name: Callable[[], str],
        snapshot: MarketSnapshot,
        clock: Clock,
    ) -> None:
        self._model = model
        self._model_name = model_name
        self._snapshot = snapshot
        self._clock = clock

    async def execute(self, history: Sequence[ChatTurn], question: ChatTurn) -> str:
        """Lanza LanguageModelError si el modelo no responde."""
        model_name = self._model_name()
        try:
            market = await self._snapshot.take()
        except Exception:
            logger.exception("Robo-advisor: no se pudo tomar la foto del mercado")
            market = ()

        instruction = build_question_instruction()
        request = build_question_request(history, question, market, self._clock.now())
        try:
            return await self._model.generate(model_name, instruction, request, web_search=True)
        except LanguageModelError as exc:
            logger.warning("Robo-advisor: busqueda web fallo (%s); se reintenta sin ella", exc)
            return await self._model.generate(model_name, instruction, request)
