from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, inspect, literal, or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from core.vault.schemas import VaultEntry, VaultKindStatistics
from core.vault.storages import VaultStorage
from infra.postgresql.models import VaultEntryModel


@dataclass(kw_only=True)
class VaultDatabaseStorage(VaultStorage):
    session: AsyncSession

    async def list_recent(self, *, author_username: str, limit: int) -> list[VaultEntry]:
        mapper = inspect(VaultEntryModel)
        branches = []
        for source_mapper in mapper.self_and_descendants:
            if not source_mapper.concrete:
                continue
            model: type[VaultEntryModel] = source_mapper.class_
            columns = [
                getattr(model, key).label(mapper.attrs[key].columns[0].name)
                for key in ("id", "display_name", "updated_at")
            ]
            branches.append(
                select(
                    *columns,
                    literal(source_mapper.polymorphic_identity).label("vault_source"),
                    model.vault_kind_expression().label("entry_kind"),
                )
                .where(model.author_username == author_username)
                .order_by(model.updated_at.desc(), model.id.desc())
                .limit(limit),
            )
        candidates = union_all(*branches).subquery("vault_candidates")
        entry = aliased(VaultEntryModel, candidates, adapt_on_names=True)
        query = (
            select(
                entry.id,
                entry.vault_source,
                candidates.c.entry_kind,
                entry.display_name,
                entry.updated_at,
            )
            .order_by(entry.updated_at.desc(), entry.vault_source.asc(), entry.id.desc())
            .limit(limit)
        )
        return [
            VaultEntry(
                id=row[0],
                source=row[1],
                kind=row[2],
                display_name=row[3],
                updated_at=row[4],
            )
            for row in (await self.session.execute(query)).tuples()
        ]

    async def list_statistics(
        self,
        *,
        author_username: str,
        from_datetime: datetime,
        to_datetime: datetime,
    ) -> list[VaultKindStatistics]:
        branches = []
        for mapper in inspect(VaultEntryModel).self_and_descendants:
            if not mapper.concrete:
                continue
            model: type[VaultEntryModel] = mapper.class_
            kind = model.vault_kind_expression()
            branches.append(
                select(
                    literal(mapper.polymorphic_identity).label("source"),
                    kind.label("entry_kind"),
                    func.count().label("total_count"),
                    func.count()
                    .filter(model.created_at.between(from_datetime, to_datetime))
                    .label("created_count"),
                    func.count()
                    .filter(
                        or_(
                            model.created_at.between(from_datetime, to_datetime),
                            model.updated_at.between(from_datetime, to_datetime),
                        ),
                    )
                    .label("active_count"),
                )
                .where(model.author_username == author_username)
                .group_by("entry_kind"),
            )
        counts = union_all(*branches).subquery("vault_counts")
        query = select(counts).order_by(counts.c.source, counts.c.entry_kind)
        return [
            VaultKindStatistics(
                source=row[0],
                kind=row[1],
                total_count=row[2],
                created_last_30_days_count=row[3],
                created_or_updated_last_30_days_count=row[4],
            )
            for row in (await self.session.execute(query)).tuples()
        ]
