from typing import Self

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    and_,
    case,
    func,
    literal,
    or_,
)
from sqlalchemy.orm import Mapped, declared_attr, mapped_column
from sqlalchemy_dev_utils.mixins.audit import AuditMixin

from core.knowledge.people.schemas import (
    PersonBirthday,
    PersonDetails,
    PersonRelationship,
    PersonRelationshipType,
    PersonRelationshipTypeCreateParams,
)
from infra.postgresql.models.base import BaseModel, TableArgs
from infra.postgresql.models.knowledge.items import KnowledgeItemModel
from infra.postgresql.models.mixins.ids import HexUuidIDMixin


class PersonDetailsModel(BaseModel):
    __tablename__ = "knowledge__person_details_model"

    item_id: Mapped[str] = mapped_column(String(length=32), primary_key=True)
    author_username: Mapped[str] = mapped_column(String(length=255))
    last_name: Mapped[str] = mapped_column(String(length=255))
    first_name: Mapped[str] = mapped_column(String(length=255))
    middle_name: Mapped[str] = mapped_column(String(length=255))
    email: Mapped[str] = mapped_column(String(length=320))
    phone: Mapped[str] = mapped_column(String(length=64))
    telegram: Mapped[str] = mapped_column(String(length=255))
    birthday_day: Mapped[int | None] = mapped_column(Integer)
    birthday_month: Mapped[int | None] = mapped_column(Integer)
    birthday_year: Mapped[int | None] = mapped_column(Integer)

    @declared_attr.directive
    @classmethod
    def __table_args__(cls) -> TableArgs:
        return (
            UniqueConstraint(
                cls.item_id,
                cls.author_username,
                name="person_details_id_author_uniq",
            ),
            ForeignKeyConstraint(
                [cls.item_id, cls.author_username],
                [KnowledgeItemModel.id, KnowledgeItemModel.author_username],
                ondelete="CASCADE",
                name="person_details_item_author_fk",
            ),
            CheckConstraint(
                or_(
                    and_(
                        cls.birthday_day.is_(None),
                        cls.birthday_month.is_(None),
                        cls.birthday_year.is_(None),
                    ),
                    and_(
                        cls.birthday_day.is_not(None),
                        cls.birthday_month.is_not(None),
                        cls.birthday_day.between(1, 31),
                        cls.birthday_month.between(1, 12),
                        or_(
                            cls.birthday_year.is_(None),
                            cls.birthday_year.between(1, 9999),
                        ),
                        cls.birthday_day
                        <= case(
                            (cls.birthday_month.in_((1, 3, 5, 7, 8, 10, 12)), 31),
                            (cls.birthday_month.in_((4, 6, 9, 11)), 30),
                            (cls.birthday_year.is_(None), 29),
                            (
                                or_(
                                    cls.birthday_year % 400 == 0,
                                    and_(
                                        cls.birthday_year % 4 == 0,
                                        cls.birthday_year % 100 != 0,
                                    ),
                                ),
                                29,
                            ),
                            else_=28,
                        ),
                        or_(
                            cls.birthday_year.is_(None),
                            func.make_date(
                                cls.birthday_year,
                                cls.birthday_month,
                                cls.birthday_day,
                            )
                            <= func.current_date(),
                        ),
                    ),
                ),
                name="person_details_birthday_check",
            ),
            Index(
                "person_details_author_name_search_idx",
                cls.author_username,
                func.lower(cls.last_name).label("last_name_lower"),
                func.lower(cls.first_name).label("first_name_lower"),
                cls.item_id,
            ),
            Index(
                "person_details_author_email_item_idx",
                cls.author_username,
                func.lower(cls.email).label("email_lower"),
                cls.item_id,
            ),
            Index(
                "person_details_author_birthday_item_idx",
                cls.author_username,
                cls.birthday_month,
                cls.birthday_day,
                cls.item_id,
            ),
            Index(
                "person_details_last_name_trgm_idx",
                func.lower(cls.last_name).label("last_name_lower_trgm"),
                postgresql_using="gin",
                postgresql_ops={"last_name_lower_trgm": "gin_trgm_ops"},
            ),
            Index(
                "person_details_first_name_trgm_idx",
                func.lower(cls.first_name).label("first_name_lower_trgm"),
                postgresql_using="gin",
                postgresql_ops={"first_name_lower_trgm": "gin_trgm_ops"},
            ),
            Index(
                "person_details_middle_name_trgm_idx",
                func.lower(cls.middle_name).label("middle_name_lower_trgm"),
                postgresql_using="gin",
                postgresql_ops={"middle_name_lower_trgm": "gin_trgm_ops"},
            ),
            Index(
                "person_details_email_trgm_idx",
                func.lower(cls.email).label("email_lower_trgm"),
                postgresql_using="gin",
                postgresql_ops={"email_lower_trgm": "gin_trgm_ops"},
            ),
            CheckConstraint(
                and_(
                    func.char_length(func.trim(cls.last_name)) > 0,
                    func.char_length(func.trim(cls.first_name)) > 0,
                ),
                name="person_details_required_names_check",
            ),
        )

    @classmethod
    def from_domain_schema(cls, *, details: PersonDetails, author_username: str) -> Self:
        return cls(
            item_id=details.item_id,
            author_username=author_username,
            last_name=details.last_name,
            first_name=details.first_name,
            middle_name=details.middle_name,
            email=details.email,
            phone=details.phone,
            telegram=details.telegram,
            birthday_day=details.birthday.day if details.birthday is not None else None,
            birthday_month=details.birthday.month if details.birthday is not None else None,
            birthday_year=details.birthday.year if details.birthday is not None else None,
        )

    def to_domain_schema(self) -> PersonDetails:
        birthday = None
        if self.birthday_day is not None and self.birthday_month is not None:
            birthday = PersonBirthday(
                day=self.birthday_day,
                month=self.birthday_month,
                year=self.birthday_year,
            )
        return PersonDetails(
            item_id=self.item_id,
            last_name=self.last_name,
            first_name=self.first_name,
            middle_name=self.middle_name,
            email=self.email,
            phone=self.phone,
            telegram=self.telegram,
            birthday=birthday,
        )


class PersonRelationshipTypeModel(HexUuidIDMixin, AuditMixin, BaseModel):
    __tablename__ = "knowledge__person_relationship_type_model"

    author_username: Mapped[str] = mapped_column(
        String(length=255),
    )
    is_symmetric: Mapped[bool] = mapped_column(Boolean)
    forward_name: Mapped[str] = mapped_column(String(length=255))
    reverse_name: Mapped[str] = mapped_column(String(length=255))

    @declared_attr.directive
    @classmethod
    def __table_args__(cls) -> TableArgs:
        return (
            UniqueConstraint(
                cls.id,
                cls.author_username,
                name="person_relationship_types_id_author_uniq",
            ),
            CheckConstraint(
                or_(
                    and_(
                        cls.is_symmetric,
                        func.char_length(func.trim(cls.forward_name)) > 0,
                        cls.reverse_name == cls.forward_name,
                    ),
                    and_(
                        ~cls.is_symmetric,
                        func.char_length(func.trim(cls.forward_name)) > 0,
                        func.char_length(func.trim(cls.reverse_name)) > 0,
                    ),
                ),
                name="person_relationship_types_names_check",
            ),
            Index(
                "person_relationship_types_author_name_id_idx",
                cls.author_username,
                func.lower(cls.forward_name).label("forward_name_lower"),
                cls.id,
            ),
        )

    @classmethod
    def from_create_params(cls, *, params: PersonRelationshipTypeCreateParams) -> Self:
        return cls(
            author_username=params.author_username,
            is_symmetric=params.is_symmetric,
            forward_name=params.forward_name,
            reverse_name=params.reverse_name,
        )

    def to_domain_schema(self) -> PersonRelationshipType:
        return PersonRelationshipType(
            id=self.id,
            author_username=self.author_username,
            is_symmetric=self.is_symmetric,
            forward_name=self.forward_name,
            reverse_name=self.reverse_name,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class PersonRelationshipModel(HexUuidIDMixin, AuditMixin, BaseModel):
    __tablename__ = "knowledge__person_relationship_model"

    author_username: Mapped[str] = mapped_column(String(length=255))
    source_person_id: Mapped[str] = mapped_column(String(length=32))
    target_person_id: Mapped[str] = mapped_column(String(length=32))
    relationship_type_id: Mapped[str] = mapped_column(String(length=32))
    note: Mapped[str] = mapped_column(Text)

    @declared_attr.directive
    @classmethod
    def __table_args__(cls) -> TableArgs:
        return (
            ForeignKeyConstraint(
                [cls.source_person_id, cls.author_username],
                [PersonDetailsModel.item_id, PersonDetailsModel.author_username],
                ondelete="CASCADE",
                name="person_relationships_source_author_fk",
            ),
            ForeignKeyConstraint(
                [cls.target_person_id, cls.author_username],
                [PersonDetailsModel.item_id, PersonDetailsModel.author_username],
                ondelete="CASCADE",
                name="person_relationships_target_author_fk",
            ),
            ForeignKeyConstraint(
                [cls.relationship_type_id, cls.author_username],
                [PersonRelationshipTypeModel.id, PersonRelationshipTypeModel.author_username],
                ondelete="RESTRICT",
                name="person_relationships_type_author_fk",
            ),
            CheckConstraint(
                cls.source_person_id != cls.target_person_id,
                name="person_relationships_not_self_check",
            ),
            Index(
                "person_relationships_author_pair_type_uniq",
                cls.author_username,
                func.least(cls.source_person_id, cls.target_person_id),
                func.greatest(cls.source_person_id, cls.target_person_id),
                cls.relationship_type_id,
                unique=True,
            ),
            Index(
                "person_relationships_author_source_idx",
                cls.author_username,
                cls.source_person_id,
                cls.id,
            ),
            Index(
                "person_relationships_author_target_idx",
                cls.author_username,
                cls.target_person_id,
                cls.id,
            ),
            Index(
                "person_relationships_author_type_id_idx",
                cls.author_username,
                cls.relationship_type_id,
                cls.id,
            ),
            CheckConstraint(
                func.char_length(cls.note) <= literal(10_000),
                name="person_relationships_note_length_check",
            ),
        )

    def to_domain_schema(
        self,
        *,
        relationship_type: PersonRelationshipType,
    ) -> PersonRelationship:
        return PersonRelationship(
            id=self.id,
            author_username=self.author_username,
            source_person_id=self.source_person_id,
            target_person_id=self.target_person_id,
            relationship_type=relationship_type,
            note=self.note,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )
