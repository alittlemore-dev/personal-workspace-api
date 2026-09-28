from sqlalchemy import Index, Integer, String
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from core.important_info.schemas import ImportantInfo
from infra.postgresql.models.base import BaseModel, TableArgs
from infra.postgresql.models.mixins.ids import HexUuidIDMixin


class ImportantInfoModel(HexUuidIDMixin, BaseModel):
    __tablename__ = "important_info_model"

    author_username: Mapped[str] = mapped_column(String(length=255))
    text: Mapped[str] = mapped_column(String(length=255))
    position: Mapped[int] = mapped_column(Integer)

    @declared_attr.directive
    @classmethod
    def __table_args__(cls) -> TableArgs:
        return (
            Index(
                "important_info_author_position_id_idx",
                cls.author_username,
                cls.position,
                cls.id,
            ),
        )

    def to_domain_schema(self) -> ImportantInfo:
        return ImportantInfo(id=self.id, text=self.text, position=self.position)
