from typing import Self

from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
    and_,
    case,
    func,
    or_,
)
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from core.knowledge.dates.schemas import (
    KnowledgeDateDetails,
    KnowledgeDatePersonLink,
    KnowledgeDateValue,
)
from infra.postgresql.models.base import BaseModel, TableArgs
from infra.postgresql.models.knowledge.items import KnowledgeItemModel
from infra.postgresql.models.knowledge.people import PersonDetailsModel


class KnowledgeDateDetailsModel(BaseModel):
    __tablename__ = "knowledge__date_details_model"

    item_id: Mapped[str] = mapped_column(String(length=32), primary_key=True)
    author_username: Mapped[str] = mapped_column(String(length=255))
    day: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)
    year: Mapped[int | None] = mapped_column(Integer)

    @declared_attr.directive
    @classmethod
    def __table_args__(cls) -> TableArgs:
        return (
            UniqueConstraint(
                cls.item_id,
                cls.author_username,
                name="date_details_id_author_uniq",
            ),
            ForeignKeyConstraint(
                [cls.item_id, cls.author_username],
                [KnowledgeItemModel.id, KnowledgeItemModel.author_username],
                ondelete="CASCADE",
                name="date_details_item_author_fk",
            ),
            CheckConstraint(
                and_(
                    cls.day.between(1, 31),
                    cls.month.between(1, 12),
                    or_(cls.year.is_(None), cls.year.between(1, 9999)),
                    cls.day
                    <= case(
                        (cls.month.in_((1, 3, 5, 7, 8, 10, 12)), 31),
                        (cls.month.in_((4, 6, 9, 11)), 30),
                        (cls.year.is_(None), 29),
                        (
                            or_(
                                cls.year % 400 == 0,
                                and_(
                                    cls.year % 4 == 0,
                                    cls.year % 100 != 0,
                                ),
                            ),
                            29,
                        ),
                        else_=28,
                    ),
                    or_(
                        cls.year.is_(None),
                        func.make_date(cls.year, cls.month, cls.day) <= func.current_date(),
                    ),
                ),
                name="date_details_calendar_check",
            ),
            Index(
                "date_details_author_calendar_item_idx",
                cls.author_username,
                cls.month,
                cls.day,
                cls.item_id,
            ),
        )

    @classmethod
    def from_domain_schema(
        cls,
        *,
        details: KnowledgeDateDetails,
        author_username: str,
    ) -> Self:
        return cls(
            item_id=details.item_id,
            author_username=author_username,
            day=details.date.day,
            month=details.date.month,
            year=details.date.year,
        )

    def to_domain_schema(self) -> KnowledgeDateDetails:
        return KnowledgeDateDetails(
            item_id=self.item_id,
            date=KnowledgeDateValue(day=self.day, month=self.month, year=self.year),
        )


class KnowledgeDatePersonModel(BaseModel):
    __tablename__ = "knowledge__date_person_model"

    date_item_id: Mapped[str] = mapped_column(String(length=32))
    person_item_id: Mapped[str] = mapped_column(String(length=32))
    author_username: Mapped[str] = mapped_column(String(length=255))

    @declared_attr.directive
    @classmethod
    def __table_args__(cls) -> TableArgs:
        return (
            PrimaryKeyConstraint(cls.date_item_id, cls.person_item_id),
            ForeignKeyConstraint(
                [cls.date_item_id, cls.author_username],
                [KnowledgeDateDetailsModel.item_id, KnowledgeDateDetailsModel.author_username],
                ondelete="CASCADE",
                name="date_people_date_author_fk",
            ),
            ForeignKeyConstraint(
                [cls.person_item_id, cls.author_username],
                [PersonDetailsModel.item_id, PersonDetailsModel.author_username],
                ondelete="CASCADE",
                name="date_people_person_author_fk",
            ),
            Index(
                "date_people_author_person_date_idx",
                cls.author_username,
                cls.person_item_id,
                cls.date_item_id,
            ),
            Index(
                "date_people_author_date_person_idx",
                cls.author_username,
                cls.date_item_id,
                cls.person_item_id,
            ),
        )

    def to_domain_schema(self) -> KnowledgeDatePersonLink:
        return KnowledgeDatePersonLink(
            date_id=self.date_item_id,
            person_id=self.person_item_id,
        )
