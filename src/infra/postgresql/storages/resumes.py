from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.resumes.exceptions import ResumeNotFoundError
from core.resumes.schemas import Resume, ResumeCreateParams, ResumeFilters
from core.resumes.storages import ResumesStorage
from infra.postgresql.models import ResumeModel


@dataclass(kw_only=True)
class ResumesDatabaseStorage(ResumesStorage):
    session: AsyncSession

    async def list_resumes(self, *, filters: ResumeFilters) -> tuple[list[Resume], int]:
        query = (
            select(ResumeModel)
            .where(ResumeModel.author_username == filters.author_username)
            .order_by(ResumeModel.updated_at.desc(), ResumeModel.id.desc())
            .offset(filters.offset)
            .limit(filters.limit)
        )
        count_query = select(func.count(ResumeModel.id)).where(
            ResumeModel.author_username == filters.author_username,
        )
        models = await self.session.scalars(query)
        total_count = (await self.session.scalar(count_query)) or 0
        return [model.to_domain_schema() for model in models], total_count

    async def get_resume(self, *, resume_id: str, author_username: str) -> Resume:
        model = await self._get_resume_model(
            resume_id=resume_id,
            author_username=author_username,
        )
        return model.to_domain_schema()

    async def create_resume(self, *, params: ResumeCreateParams) -> Resume:
        model = ResumeModel.from_create_params(params=params)
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return model.to_domain_schema()

    async def update_resume(self, *, resume: Resume) -> Resume:
        model = await self._get_resume_model(
            resume_id=resume.id,
            author_username=resume.author_username,
        )
        model.update_from_domain_schema(resume=resume)
        await self.session.flush()
        return model.to_domain_schema()

    async def delete_resume(self, *, resume_id: str, author_username: str) -> None:
        model = await self._get_resume_model(
            resume_id=resume_id,
            author_username=author_username,
        )
        await self.session.delete(model)
        await self.session.flush()

    async def _get_resume_model(self, *, resume_id: str, author_username: str) -> ResumeModel:
        query = select(ResumeModel).where(
            ResumeModel.id == resume_id,
            ResumeModel.author_username == author_username,
        )
        model = await self.session.scalar(query)
        if model is None:
            raise ResumeNotFoundError
        return model
