from typing import Awaitable, Callable, Protocol

from domain.value_objects.daily_time import DailyTime

Job = Callable[[], Awaitable[None]]


class Scheduler(Protocol):
    def schedule_daily(self, job_id: str, at: DailyTime, job: Job) -> None: ...
    def start(self) -> None: ...
    def shutdown(self) -> None: ...