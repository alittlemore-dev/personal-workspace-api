from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from core.files.schemas import StoredFile
from infra.postgresql.models import FileModel


@dataclass(kw_only=True)
class StorageHelper:
    session: AsyncSession

    async def create_file(self, file: StoredFile) -> FileModel:
        model = FileModel.from_domain_schema(file)
        self.session.add(model)
        await self.session.flush()
        return model
