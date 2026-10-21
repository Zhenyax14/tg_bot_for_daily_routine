"""Puerto de salida del topic multi-bot: publicar como uno de los bots."""
from __future__ import annotations

from typing import Mapping, Protocol

from domain.value_objects.squad_message import SquadMember


class SquadDeliveryError(Exception):
    """No se pudo publicar el mensaje del bot."""


class SquadGateway(Protocol):
    def members(self) -> Mapping[int, SquadMember]:
        """Bots conectados ahora mismo, por slot."""
        ...

    async def typing(self, slot: int) -> None: ...

    async def send(self, slot: int, text: str, reply_to: int) -> tuple[int, ...]:
        """Publica `text` (Markdown) como respuesta a `reply_to`; devuelve los
        ids de los mensajes enviados (puede trocearse en varios)."""
        ...

    async def report_failure(self, slot: int, reply_to: int) -> None:
        """Avisa en el topic de que el bot no pudo responder."""
        ...
