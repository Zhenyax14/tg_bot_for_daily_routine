"""Caso de uso: si hoy es festivo en algun pais vigilado, felicita en el grupo.

Reutiliza SendMessage (toda salida del sistema pasa por el) y GetTodaysHolidays.
El texto de la felicitacion se inyecta como funcion (greeter) para no meter
cadenas de idioma en la capa de aplicacion. Si hoy no hay festivo, no envia nada.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence

from application.use_cases.get_todays_holidays import GetTodaysHolidays
from application.use_cases.send_message import SendMessage
from domain.value_objects.holiday import Holiday


class AnnounceTodaysHolidays:
    def __init__(
        self,
        get_todays_holidays: GetTodaysHolidays,
        send_message: SendMessage,
        greeter: Callable[[Sequence[Holiday]], str],
    ) -> None:
        self._get_todays_holidays = get_todays_holidays
        self._send_message = send_message
        self._greeter = greeter

    async def execute(self) -> None:
        holidays = await self._get_todays_holidays.execute()
        if not holidays:
            return
        await self._send_message.execute(self._greeter(holidays))