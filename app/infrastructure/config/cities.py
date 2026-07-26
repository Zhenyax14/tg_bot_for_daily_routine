"""Ciudades del comando /time, definidas como datos (como los mensajes).

Anadir una ciudad es una linea. La clave IANA es la unica fuente de verdad del
cambio invierno/verano:

  - Europe/Madrid       -> CET/CEST, SI aplica horario de verano.
  - Europe/Moscow       -> MSK (UTC+3), sin horario de verano desde 2014.
  - Asia/Yekaterinburg  -> YEKT (UTC+5), sin horario de verano. Cheliabinsk
                           pertenece a esta zona.
"""
from __future__ import annotations

from domain.value_objects.city import City

WORLD_CLOCK_CITIES: tuple[City, ...] = (
    City("Мадрид", "Europe/Madrid"),
    City("Питер", "Europe/Moscow"),
    City("Челябинск", "Asia/Yekaterinburg"),
)