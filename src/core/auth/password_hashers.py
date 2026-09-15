from abc import ABC, abstractmethod

from core.schemas import Secret


class PasswordHasher(ABC):
    @abstractmethod
    def verify(self, *, password: Secret[str], password_hash: Secret[str]) -> bool:
        raise NotImplementedError
