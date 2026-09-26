from abc import ABC, abstractmethod


class ReminderSender(ABC):
    @abstractmethod
    async def send(self, *, private_chat_id: int, text: str) -> None: ...


class PermanentReminderSendError(Exception):
    pass


class RetryableReminderSendError(Exception):
    def __init__(self, *, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
