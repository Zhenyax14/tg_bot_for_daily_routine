from apscheduler.schedulers.asyncio import AsyncIOScheduler

from application.ports.scheduler import Job
from domain.value_objects.daily_time import DailyTime

_MISFIRE_GRACE_SECONDS = 300


class APSchedulerAdapter:
    def __init__(self, timezone: str) -> None:
        self._scheduler = AsyncIOScheduler(timezone=timezone)

    def schedule_daily(self, job_id: str, at: DailyTime, job: Job) -> None:
        self._scheduler.add_job(
            job,
            trigger="cron",
            hour=at.hour,
            minute=at.minute,
            id=job_id,
            replace_existing=True,
            misfire_grace_time=_MISFIRE_GRACE_SECONDS,
        )

    def schedule_interval(self, job_id: str, minutes: int, job: Job) -> None:
        self._scheduler.add_job(
            job,
            trigger="interval",
            minutes=minutes,
            id=job_id,
            replace_existing=True,
            misfire_grace_time=_MISFIRE_GRACE_SECONDS,
        )

    def start(self) -> None:
        self._scheduler.start()

    def shutdown(self) -> None:
        self._scheduler.shutdown(wait=False)