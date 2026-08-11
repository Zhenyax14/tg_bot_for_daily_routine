from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import quote

from config.errors import ConfigError

_REQUIRED = (
    "TELEGRAM_BOT_TOKEN",
    "CHAT_ID",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "ADMIN_PASSWORD",
)
_TRUTHY = {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str
    chat_id: str
    thread_id: int | None
    timezone: str
    dry_run: bool
    startup_message: str
    database_url: str
    spain_municipio: str
    web_host: str
    web_port: int
    admin_user: str
    admin_password: str

    @classmethod
    def from_env(cls) -> Settings:
        missing = [name for name in _REQUIRED if not os.getenv(name, "").strip()]
        if missing:
            raise ConfigError("Faltan variables de entorno: " + ", ".join(missing))

        raw_thread = os.getenv("THREAD_ID", "").strip()
        if raw_thread and not raw_thread.lstrip("-").isdigit():
            raise ConfigError(f"THREAD_ID debe ser numérico, recibido {raw_thread!r}")

        raw_port = os.getenv("WEB_PORT", "8080").strip()
        if not raw_port.isdigit():
            raise ConfigError(f"WEB_PORT debe ser numérico, recibido {raw_port!r}")

        raw_municipio = os.getenv("SPAIN_MUNICIPIO", "03031").strip()
        if not (raw_municipio.isdigit() and len(raw_municipio) == 5):
            raise ConfigError(
                f"SPAIN_MUNICIPIO debe ser un código INE de 5 dígitos, recibido {raw_municipio!r}"
            )

        # DATABASE_URL se construye aqui, NUNCA se duplica en .env: asi la
        # contrasena vive en un unico sitio (POSTGRES_PASSWORD) y no puede
        # desincronizarse entre dos variables escritas a mano. La contrasena
        # se url-encode para que caracteres especiales (@ : / % #) no rompan
        # el DSN.
        pg_user = os.environ["POSTGRES_USER"].strip()
        pg_password = os.environ["POSTGRES_PASSWORD"]
        pg_db = os.environ["POSTGRES_DB"].strip()
        pg_host = os.getenv("POSTGRES_HOST", "postgres").strip()
        pg_port = os.getenv("POSTGRES_PORT", "5432").strip()
        database_url = (
            f"postgresql://{quote(pg_user, safe='')}:{quote(pg_password, safe='')}"
            f"@{pg_host}:{pg_port}/{quote(pg_db, safe='')}"
        )

        return cls(
            bot_token=os.environ["TELEGRAM_BOT_TOKEN"].strip(),
            chat_id=os.environ["CHAT_ID"].strip(),
            thread_id=int(raw_thread) if raw_thread else None,
            timezone=os.getenv("TZ", "Europe/Madrid"),
            dry_run=os.getenv("DRY_RUN", "").strip().lower() in _TRUTHY,
            startup_message=os.getenv("STARTUP_MESSAGE", "Инициализируюсь..."),
            database_url=database_url,
            spain_municipio=raw_municipio,
            web_host=os.getenv("WEB_HOST", "0.0.0.0").strip(),
            web_port=int(raw_port),
            admin_user=os.getenv("ADMIN_USER", "admin").strip(),
            admin_password=os.environ["ADMIN_PASSWORD"]
        )