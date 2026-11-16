"""Puerto de salida: titulares recientes sobre unos instrumentos y sobre el
mercado en general. Lo usa el robo-advisor para explicar los movimientos sin
depender de la busqueda web del modelo (que puede no tener cuota).

Una fuente caida no debe tumbar el analisis: el adaptador devuelve lista
vacia (y lo registra) en vez de lanzar."""
from __future__ import annotations

from typing import Protocol, Sequence

from domain.value_objects.instrument import Instrument
from domain.value_objects.news_headline import NewsHeadline


class NewsProvider(Protocol):
    async def latest(self, instruments: Sequence[Instrument]) -> list[NewsHeadline]:
        """Titulares de las ultimas ~24 h sobre `instruments` y sobre los
        mercados a los que pertenecen (sin instrumentos: mercado general)."""
        ...
