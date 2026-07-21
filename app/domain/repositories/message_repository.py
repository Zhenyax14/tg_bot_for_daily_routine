from typing import Protocol, Sequence

from domain.entities.scheduled_message import ScheduledMessage


class MessageRepository(Protocol):
    def all(self) -> Sequence[ScheduledMessage]: ...