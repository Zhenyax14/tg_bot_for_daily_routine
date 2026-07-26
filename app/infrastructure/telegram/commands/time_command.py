"""Comando /time: hora actual de las ciudades configuradas.

Capa driving (entrada): el handler solo traduce el Update a una llamada al
caso de uso y devuelve el texto formateado. Cero logica de negocio aqui (SRP).
"""
from __future__ import annotations

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from application.use_cases.get_world_times import GetWorldTimes
from infrastructure.telegram.formatting import format_world_times


class TimeCommand:
    """Handler de /time. Recibe el caso de uso por constructor (DIP)."""

    def __init__(self, get_world_times: GetWorldTimes) -> None:
        self._get_world_times = get_world_times

    async def __call__(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not update.effective_chat:
            return
        times = self._get_world_times.execute()
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=format_world_times(times),
            parse_mode=ParseMode.HTML,
            message_thread_id=(
                update.effective_message.message_thread_id
                if update.effective_message
                else None
            ),
        )