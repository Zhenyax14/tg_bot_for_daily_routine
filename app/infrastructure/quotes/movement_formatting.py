from __future__ import annotations

from domain.services.price_movement_policy import Movement
from domain.value_objects.instrument import Instrument


def format_movement_alert(instrument: Instrument, movement: Movement) -> str:
    is_up = movement.percent >= 0
    icon = "🟢🔺" if is_up else "🔴🔻"
    direction = "рост" if is_up else "падение"
    sign = "+" if is_up else ""
    currency = instrument.currency
    return (
        f"{icon} <b>{instrument.label}</b>\n"
        f"{movement.reference:.2f}{currency} → {movement.current:.2f}{currency}"
        f" — {direction} {sign}{movement.percent:.1f}%"
    )
