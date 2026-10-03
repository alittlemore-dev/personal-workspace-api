from typing import ClassVar

from sqlalchemy import String, literal
from sqlalchemy.ext.declarative import AbstractConcreteBase
from sqlalchemy.orm import DeclarativeBase, InstrumentedAttribute, Mapped, mapped_column
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy_dev_utils.mixins.audit import AuditMixin

from infra.postgresql.models.base import BaseModel
from infra.postgresql.models.mixins.ids import HexUuidIDMixin


class VaultDeclarativeBase(DeclarativeBase):
    registry = BaseModel.registry


class VaultEntryModel(AbstractConcreteBase, HexUuidIDMixin, AuditMixin, VaultDeclarativeBase):
    strict_attrs = True
    _concrete_discriminator_name = "vault_source"

    vault_source: ClassVar[InstrumentedAttribute[str]]
    author_username: Mapped[str] = mapped_column(String(length=255))
    display_name: Mapped[str] = mapped_column(String(length=255))

    @classmethod
    def vault_kind_expression(cls) -> ColumnElement[str]:
        return literal(cls.__mapper__.polymorphic_identity, type_=String)
