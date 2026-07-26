"""Textos de festivos, en ruso. Presentacion (infraestructura)."""
from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from domain.value_objects.holiday import Holiday

_FLAGS = {"ES": "\U0001F1EA\U0001F1F8", "RU": "\U0001F1F7\U0001F1FA"}

# Meses en genitivo ruso, para no depender del locale del contenedor.
_MONTHS_RU = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)


def _ru_date(d: date) -> str:
    return f"{d.day} {_MONTHS_RU[d.month - 1]}"


def format_holiday_greeting(holidays: Sequence[Holiday]) -> str:
    lines = ["\U0001F389 Сегодня праздник!", ""]
    for h in holidays:
        flag = _FLAGS.get(h.country, "\U0001F4C5")
        lines.append(f"{flag} {h.local_name}")
    return "\n".join(lines)


def format_upcoming_holidays(holidays: Sequence[Holiday]) -> str:
    if not holidays:
        return "\U0001F4C5 Ближайших праздников нет."
    lines = ["\U0001F4C5 Ближайшие праздники", ""]
    for h in holidays:
        flag = _FLAGS.get(h.country, "\U0001F4C5")
        lines.append(f"{flag} {_ru_date(h.day)} — {h.local_name}")
    return "\n".join(lines)