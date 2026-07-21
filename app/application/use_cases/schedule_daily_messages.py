import logging

from application.ports.scheduler import Scheduler
from application.use_cases.send_message import SendMessage
from domain.entities.scheduled_message import ScheduledMessage
from domain.repositories.message_repository import MessageRepository

logger = logging.getLogger(__name__)


class ScheduleDailyMessages:
    def __init__(
        self,
        repository: MessageRepository,
        scheduler: Scheduler,
        send_message: SendMessage,
    ) -> None:
        self._repository = repository
        self._scheduler = scheduler
        self._send_message = send_message

    def execute(self) -> None:
        for message in self._repository.all():
            self._scheduler.schedule_daily(
                job_id=message.id,
                at=message.at,
                job=self._job_for(message),
            )
            logger.info("Programado %s a las %s", message.id, message.at)

    def _job_for(self, message: ScheduledMessage):
        async def job() -> None:
            await self._send_message.execute(message.text)

        return job