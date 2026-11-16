"""Caso de uso: revision periodica del mercado por el robo-advisor (el bot
principal).

Cada N minutos (30 en main.py) toma la foto del mercado y la compara con la
de la revision anterior. Los instrumentos que se han movido al menos
`threshold_percent` (2% por defecto, por debajo del ±5% de las alertas) son
"movimientos notables": si hay alguno, el robo-advisor publica un analisis de ellos
en el contexto de todo el mercado. Si no hay ninguno (o los mercados estan
cerrados y nada se mueve), no se publica nada.

La primera revision tras arrancar solo fija la base, en silencio (igual que
la primera cotizacion del dia en las alertas): nunca inventa saltos.
"""
from __future__ import annotations

import logging

from application.services.market_analysis_prompt import REVIEW
from application.services.market_snapshot import MarketSnapshot
from application.use_cases.analyze_market_moves import AnalyzeMarketMoves
from domain.services.price_movement_policy import PriceMovementPolicy
from domain.value_objects.market_moves import MarketMoves, PriceAlert

logger = logging.getLogger(__name__)


class ReviewMarket:
    def __init__(
        self,
        snapshot: MarketSnapshot,
        analyzer: AnalyzeMarketMoves,
        threshold_percent: float = 2.0,
    ) -> None:
        self._snapshot = snapshot
        self._analyzer = analyzer
        self._policy = PriceMovementPolicy(threshold_percent)
        self._previous: dict[str, float] = {}

    async def execute(self) -> None:
        market = await self._snapshot.take()
        movers: list[PriceAlert] = []
        for quote in market:
            previous = self._previous.get(quote.instrument.symbol)
            if previous is not None and self._policy.is_significant(previous, quote.price):
                movers.append(PriceAlert(quote, self._policy.movement(previous, quote.price)))

        # Si una cotizacion falta en este ciclo, se conserva su base anterior.
        self._previous.update({quote.instrument.symbol: quote.price for quote in market})
        if not movers:
            logger.info("Revision de mercado: sin movimientos notables")
            return
        await self._analyzer.execute(MarketMoves(tuple(movers), market), REVIEW)
