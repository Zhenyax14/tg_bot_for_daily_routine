"""Value object: un titular de noticias (titulo, medio, fecha, enlace)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class NewsHeadline:
    title: str
    source: str
    published_at: datetime | None
    url: str
