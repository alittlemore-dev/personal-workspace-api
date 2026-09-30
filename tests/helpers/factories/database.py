from sqlalchemy.ext.asyncio import AsyncSession

from core.finance.enums import FinanceKind
from infra.postgresql.models.finance import FinanceTemplateCategoryModel


class DatabaseFactoryHelper:
    @classmethod
    def finance_template_category(
        cls,
        key: str = "food",
        kind: FinanceKind = FinanceKind.EXPENSE,
        name_ru: str = "Еда",
        name_en: str = "Food",
        position: int = 0,
    ) -> FinanceTemplateCategoryModel:
        return FinanceTemplateCategoryModel(
            key=key,
            kind=kind,
            name_ru=name_ru,
            name_en=name_en,
            position=position,
        )

    @classmethod
    async def seed_finance_templates(cls, session: AsyncSession) -> None:
        session.add_all(
            [
                cls.finance_template_category(),
                cls.finance_template_category(
                    key="salary",
                    kind=FinanceKind.INCOME,
                    name_ru="Зарплата",
                    name_en="Salary",
                ),
            ],
        )
        await session.flush()
