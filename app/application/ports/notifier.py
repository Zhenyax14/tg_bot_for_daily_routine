from typing import Protocol


class Notifier(Protocol):
    async def send(self, text: str) -> None: ...