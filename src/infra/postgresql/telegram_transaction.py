from dataclasses import dataclass

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from core.telegram.exceptions import TelegramServiceError
from core.telegram.storages import TelegramTransaction


@dataclass(kw_only=True, slots=True)
class TelegramDatabaseTransaction(TelegramTransaction):
    session: AsyncSession

    async def commit(self) -> None:
        try:
            await self.session.commit()
        except SQLAlchemyError as exc:
            await self.session.rollback()
            raise TelegramServiceError from exc

    async def rollback(self) -> None:
        await self.session.rollback()
