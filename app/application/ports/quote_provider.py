from __future__ import annotations

from typing import Iterable, Protocol

from domain.value_objects.instrument import Instrument
from domain.value_objects.quote import Quote


class QuoteProvider(Protocol):
    async def fetch(self, instruments: Iterable[Instrument]) -> list[Quote]: ...
