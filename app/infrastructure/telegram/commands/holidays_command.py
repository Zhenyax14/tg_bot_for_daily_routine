"""Comando /holidays: festivos de los proximos dias en ES y RU.

Capa driving: traduce el Update en una llamada al caso de uso y envia el texto.
"""
from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from application.use_cases.get_upcoming_holidays import GetUpcomingHolidays
from infrastructure.telegram.holiday_formatting import format_upcoming_holidays


class HolidaysCommand:
    def __init__(self, get_upcoming_holidays: GetUpcomingHolidays) -> None:
        self._get_upcoming_holidays = get_upcoming_holidays

    async def __call__(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not update.effective_chat:
            return
        holidays = await self._get_upcoming_holidays.execute()
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=format_upcoming_holidays(holidays),
            message_thread_id=(
                update.effective_message.message_thread_id
                if update.effective_message
                else None
            ),
        )