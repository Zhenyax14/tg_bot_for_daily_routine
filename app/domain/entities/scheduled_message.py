from dataclasses import dataclass

from domain.value_objects.daily_time import DailyTime


@dataclass(frozen=True, slots=True)
class ScheduledMessage:
    id: str
    at: DailyTime
    text: str