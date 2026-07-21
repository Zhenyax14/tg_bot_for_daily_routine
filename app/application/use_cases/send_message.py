from application.ports.notifier import Notifier


class SendMessage:
    """Único caso de uso de envío. Da igual el texto y da igual el canal."""

    def __init__(self, notifier: Notifier) -> None:
        self._notifier = notifier

    async def execute(self, text: str) -> None:
        await self._notifier.send(text)