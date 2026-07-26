"""Formato de presentacion para /time (monoespaciado con <pre>)."""
from __future__ import annotations

from collections.abc import Sequence

from application.use_cases.get_world_times import CityTime

_FLAGS = {
    "Europe/Madrid": "\U0001F1EA\U0001F1F8",       # ES
    "Europe/Moscow": "\U0001F1F7\U0001F1FA",       # RU
    "Asia/Yekaterinburg": "\U0001F1F7\U0001F1FA",  # RU
}


def format_world_times(times: Sequence[CityTime]) -> str:
    name_w = max(len(t.city.name) for t in times)
    rows = []
    for t in times:
        flag = _FLAGS.get(t.city.timezone_key, "\U0001F553")
        hhmm = t.local_time.strftime("%H:%M")
        rows.append(f"{flag} {t.city.name.ljust(name_w)}   {hhmm}")
    body = "\n".join(rows)
    return f"\U0001F552 Текущее время\n<pre>{body}</pre>"