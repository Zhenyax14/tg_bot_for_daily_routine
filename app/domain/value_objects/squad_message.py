"""Value objects del topic multi-bot.

`SquadMember`: un bot conectado (slot + su cuenta de Telegram).
`SquadMessage`: un mensaje del topic, de una persona (`bot_slot=None`) o de
uno de los bots. `reply_to` es el mensaje al que responde, si lo hay: es lo
que encadena los mensajes en una misma conversacion ("tema")."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SquadMember:
    slot: int
    user_id: int
    username: str
    name: str


@dataclass(frozen=True)
class SquadMessage:
    message_id: int
    author: str
    text: str
    bot_slot: int | None = None
    reply_to: int | None = None
