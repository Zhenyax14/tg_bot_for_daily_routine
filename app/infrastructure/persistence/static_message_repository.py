from typing import Sequence

from domain.entities.scheduled_message import ScheduledMessage
from domain.value_objects.daily_time import DailyTime

_MESSAGES: tuple[tuple[str, str, str], ...] = (
    ("morning-greeting", "07:00", "От имени моего создателя желаю вам доброго утро, друзья"),
    ("game-chance", "07:15", "Шанс игры @Duhastikx @SamVimesHimself @Niktia_Bordin"),
    ("good-night", "22:00", "Спокойной ночи, друзья"),
)


class StaticMessageRepository:
    def all(self) -> Sequence[ScheduledMessage]:
        return tuple(
            ScheduledMessage(id=id_, at=DailyTime.parse(at), text=text)
            for id_, at, text in _MESSAGES
        )