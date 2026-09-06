from __future__ import annotations

import logging
from typing import Awaitable, Callable

from application.ports.quote_provider import QuoteProvider
from application.services.instrument_settings_service import InstrumentSettingsService
from application.services.reference_prices import ReferencePrices
from domain.services.price_movement_policy import Movement, PriceMovementPolicy
from domain.value_objects.instrument import Instrument

AlertCallback = Callable[[Instrument, Movement], Awaitable[None]]

logger = logging.getLogger(__name__)


class CheckPriceMovements:
    """Un ciclo de vigilancia: obtiene cotizaciones y dispara alertas de
    movimientos significativos, encadenando la referencia (trail ±5%). Los
    instrumentos habilitados se releen en cada ciclo, así que un cambio hecho
    desde el panel de administración se aplica sin reiniciar el bot."""

    def __init__(
        self,
        instrument_settings: InstrumentSettingsService,
        provider: QuoteProvider,
        references: ReferencePrices,
        policy: PriceMovementPolicy,
        alert: AlertCallback,
    ) -> None:
        self._instrument_settings = instrument_settings
        self._provider = provider
        self._references = references
        self._policy = policy
        self._alert = alert

    async def execute(self) -> None:
        instruments = self._instrument_settings.enabled_instruments()
        quotes = await self._provider.fetch(instruments)
        by_symbol = {instrument.symbol: instrument for instrument in instruments}
        for quote in quotes:
            instrument = by_symbol.get(quote.symbol)
            if instrument is None:
                continue

            reference = self._references.reference_for(quote.symbol)
            if reference is None:
                self._references.set_reference(quote.symbol, quote.price)
                continue

            if not self._policy.is_significant(reference, quote.price):
                continue

            movement = self._policy.movement(reference, quote.price)
            self._references.set_reference(quote.symbol, quote.price)
            try:
                await self._alert(instrument, movement)
            except Exception:
                logger.exception("Fallo al enviar la alerta de %s", quote.symbol)
