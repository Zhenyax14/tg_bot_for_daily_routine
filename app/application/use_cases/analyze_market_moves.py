"""Caso de uso: el robo-advisor (el bot principal) analiza movimientos de
mercado y publica el analisis en el hilo de alertas. La causa sale de los
titulares recientes (NewsProvider) y, si hay cuota, de la busqueda web del
modelo. Su identidad es propia y estrategica (ver
market_analysis_prompt): no usa las instrucciones del asistente de /admin/ai,
que es para divertir; de alli solo toma el modelo (`model_name`).

Lo usan dos disparadores:
- el evento que emite CheckPriceMovements cuando un ciclo dispara alertas
  (estilo webhook: el evento llega, se reacciona) -> tarea ALERT;
- la revision periodica de ReviewMarket (cada 30 min) -> tarea REVIEW.

Las alertas clasicas se siguen publicando igual; esto es un mensaje aparte.
Devuelve False si no se publico (el modelo no respondio o Telegram rechazo
el mensaje).
Si la busqueda web falla (modelo o cuota sin grounding), se reintenta una vez
sin ella.
"""
from __future__ import annotations

import logging
from typing import Callable

from application.ports.clock import Clock
from application.ports.language_model import LanguageModel, LanguageModelError
from application.ports.news_provider import NewsProvider
from application.ports.notifier import Notifier
from application.services.market_analysis_prompt import (
    ALERT,
    Task,
    build_analysis_instruction,
    build_analysis_request,
)
from domain.value_objects.market_moves import MarketMoves

logger = logging.getLogger(__name__)


class AnalyzeMarketMoves:
    def __init__(
        self,
        model: LanguageModel,
        model_name: Callable[[], str],
        publisher: Notifier,
        clock: Clock,
        news: NewsProvider,
    ) -> None:
        self._model = model
        self._model_name = model_name
        self._publisher = publisher
        self._clock = clock
        self._news = news

    async def execute(self, moves: MarketMoves, task: Task = ALERT) -> bool:
        model_name = self._model_name()
        instruction = build_analysis_instruction(task)
        headlines = await self._news.latest([alert.instrument for alert in moves.alerts])
        request = build_analysis_request(moves, self._clock.now(), task, headlines)
        try:
            analysis = await self._model.generate(model_name, instruction, request, web_search=True)
        except LanguageModelError as exc:
            logger.warning("Analisis de mercado con busqueda web fallo (%s); se reintenta sin ella", exc)
            try:
                analysis = await self._model.generate(model_name, instruction, request)
            except LanguageModelError as exc2:
                logger.error("Analisis de mercado: el modelo no respondio: %s", exc2)
                return False

        try:
            await self._publisher.send(analysis)
        except Exception:
            logger.exception("Analisis de mercado: no se pudo publicar")
            return False
        logger.info(
            "Analisis de mercado (%s) publicado: %s",
            task, ", ".join(alert.instrument.symbol for alert in moves.alerts),
        )
        return True
