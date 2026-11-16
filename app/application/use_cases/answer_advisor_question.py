"""Caso de uso: alguien habla con el robo-advisor (el bot principal) en el
hilo de alertas ("hazme un analisis del mercado ahora").

Toma una foto fresca del mercado vigilado, la anexa a la pregunta y se la
pasa al modelo (`model_name`, el elegido en /admin/ai) con la identidad
estrategica del robo-advisor (no las instrucciones de /admin/ai) y
titulares de las ultimas 24 h (NewsProvider): de los instrumentos del
catalogo que se nombran en la pregunta ("Tesla", "SBER"...) y del mercado en
general. Ademas pide busqueda web al modelo; si falla, se reintenta sin ella.
Si no hay cotizaciones (proveedores caidos) se contesta igual.
"""
from __future__ import annotations

import logging
import re
from typing import Callable, Sequence

from application.ports.clock import Clock
from application.ports.language_model import LanguageModel, LanguageModelError
from application.ports.news_provider import NewsProvider
from application.services.market_analysis_prompt import build_question_instruction, build_question_request
from application.services.market_snapshot import MarketSnapshot
from domain.value_objects.chat_turn import ChatTurn
from domain.value_objects.instrument import Instrument

logger = logging.getLogger(__name__)


class AnswerAdvisorQuestion:
    def __init__(
        self,
        model: LanguageModel,
        model_name: Callable[[], str],
        snapshot: MarketSnapshot,
        clock: Clock,
        news: NewsProvider,
        catalog: Sequence[Instrument],
    ) -> None:
        self._model = model
        self._model_name = model_name
        self._snapshot = snapshot
        self._clock = clock
        self._news = news
        self._catalog = tuple(catalog)

    async def execute(self, history: Sequence[ChatTurn], question: ChatTurn) -> str:
        """Lanza LanguageModelError si el modelo no responde."""
        model_name = self._model_name()
        try:
            market = await self._snapshot.take()
        except Exception:
            logger.exception("Robo-advisor: no se pudo tomar la foto del mercado")
            market = ()

        instruction = build_question_instruction()
        headlines = await self._news.latest(self._mentioned(question.text))
        request = build_question_request(history, question, market, self._clock.now(), headlines)
        try:
            return await self._model.generate(model_name, instruction, request, web_search=True)
        except LanguageModelError as exc:
            logger.warning("Robo-advisor: busqueda web fallo (%s); se reintenta sin ella", exc)
            return await self._model.generate(model_name, instruction, request)

    def _mentioned(self, text: str) -> list[Instrument]:
        """Instrumentos del catalogo nombrados en la pregunta (por etiqueta,
        sin lo que va entre parentesis, o por ticker como palabra suelta)."""
        lowered = text.lower()
        found = []
        for instrument in self._catalog:
            label = re.sub(r"\s*\(.*?\)", "", instrument.label).split("/")[0].strip().lower()
            by_label = len(label) >= 3 and label in lowered
            by_symbol = re.search(rf"(?<![\w-]){re.escape(instrument.symbol.lower())}(?![\w-])", lowered)
            if by_label or by_symbol:
                found.append(instrument)
        return found
