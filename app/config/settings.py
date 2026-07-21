from __future__ import annotations

import os
from dataclasses import dataclass

from config.errors import ConfigError

_REQUIRED = ("TELEGRAM_BOT_TOKEN", "CHAT_ID")
_TRUTHY = {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str
    chat_id: str
    thread_id: int | None
    timezone: str
    dry_run: bool
    startup_message: str

    @classmethod
    def from_env(cls) -> Settings:
        missing = [name for name in _REQUIRED if not os.getenv(name, "").strip()]
        if missing:
            raise ConfigError("Faltan variables de entorno: " + ", ".join(missing))

        raw_thread = os.getenv("THREAD_ID", "").strip()
        if raw_thread and not raw_thread.lstrip("-").isdigit():
            raise ConfigError(f"THREAD_ID debe ser numérico, recibido {raw_thread!r}")

        return cls(
            bot_token=os.environ["TELEGRAM_BOT_TOKEN"].strip(),
            chat_id=os.environ["CHAT_ID"].strip(),
            thread_id=int(raw_thread) if raw_thread else None,
            timezone=os.getenv("TZ", "Europe/Madrid"),
            dry_run=os.getenv("DRY_RUN", "").strip().lower() in _TRUTHY,
            startup_message=os.getenv("STARTUP_MESSAGE", "Инициализируюсь..."),
        )