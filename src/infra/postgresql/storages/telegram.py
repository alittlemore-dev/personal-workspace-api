from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.telegram.enums import TelegramConnectionState
from core.telegram.exceptions import TelegramAccessError, TelegramInvitationError
from core.telegram.schemas import (
    TelegramConnection,
    TelegramInvitation,
    TelegramParticipant,
)
from core.telegram.storages import TelegramStorage
from infra.postgresql.models import (
    TelegramConnectionModel,
    TelegramInvitationModel,
)


@dataclass(kw_only=True)
class TelegramDatabaseStorage(TelegramStorage):
    session: AsyncSession

    async def count_recent_invitations(self, *, owner_username: str, since: datetime) -> int:
        await self.session.execute(
            select(func.pg_advisory_xact_lock(func.hashtext(owner_username))),
        )
        count = await self.session.scalar(
            select(func.count(TelegramInvitationModel.id)).where(
                TelegramInvitationModel.owner_username == owner_username,
                TelegramInvitationModel.created_at >= since,
            ),
        )
        return count or 0

    async def replace_invitation(
        self,
        *,
        owner_username: str,
        token_hash: str,
        label: str,
        expires_at: datetime,
        now: datetime,
    ) -> TelegramInvitation:
        await self.session.execute(
            update(TelegramInvitationModel)
            .where(
                TelegramInvitationModel.owner_username == owner_username,
                TelegramInvitationModel.used_at.is_(None),
                TelegramInvitationModel.cancelled_at.is_(None),
            )
            .values(cancelled_at=now),
        )
        model = TelegramInvitationModel(
            owner_username=owner_username,
            token_hash=token_hash,
            label=label,
            created_at=now,
            expires_at=expires_at,
            used_at=None,
            cancelled_at=None,
        )
        self.session.add(model)
        await self.session.flush()
        return model.to_domain_schema()

    async def get_invitation(self, *, token_hash: str, lock: bool) -> TelegramInvitation | None:
        query = select(TelegramInvitationModel).where(
            TelegramInvitationModel.token_hash == token_hash,
        )
        if lock:
            query = query.with_for_update()
        model = await self.session.scalar(query)
        return model.to_domain_schema() if model is not None else None

    async def consume_invitation(self, *, invitation_id: str, now: datetime) -> None:
        consumed_id = await self.session.scalar(
            update(TelegramInvitationModel)
            .where(
                TelegramInvitationModel.id == invitation_id,
                TelegramInvitationModel.used_at.is_(None),
                TelegramInvitationModel.cancelled_at.is_(None),
                TelegramInvitationModel.expires_at > now,
            )
            .values(used_at=now)
            .returning(TelegramInvitationModel.id),
        )
        if consumed_id is None:
            raise TelegramInvitationError

    async def cancel_invitation(
        self,
        *,
        owner_username: str,
        invitation_id: str,
        now: datetime,
    ) -> None:
        cancelled_id = await self.session.scalar(
            update(TelegramInvitationModel)
            .where(
                TelegramInvitationModel.id == invitation_id,
                TelegramInvitationModel.owner_username == owner_username,
                TelegramInvitationModel.used_at.is_(None),
                TelegramInvitationModel.cancelled_at.is_(None),
            )
            .values(cancelled_at=now)
            .returning(TelegramInvitationModel.id),
        )
        if cancelled_id is None:
            raise TelegramInvitationError

    async def list_invitations(
        self,
        *,
        owner_username: str,
        now: datetime,
    ) -> list[TelegramInvitation]:
        models = await self.session.scalars(
            select(TelegramInvitationModel)
            .where(
                TelegramInvitationModel.owner_username == owner_username,
                TelegramInvitationModel.used_at.is_(None),
                TelegramInvitationModel.cancelled_at.is_(None),
                TelegramInvitationModel.expires_at > now,
            )
            .order_by(TelegramInvitationModel.created_at.desc()),
        )
        return [model.to_domain_schema() for model in models]

    async def list_connections(self, *, owner_username: str) -> list[TelegramConnection]:
        models = await self.session.scalars(
            select(TelegramConnectionModel)
            .where(
                TelegramConnectionModel.owner_username == owner_username,
            )
            .order_by(
                TelegramConnectionModel.requested_at.desc(),
                TelegramConnectionModel.id.desc(),
            ),
        )
        return [model.to_domain_schema() for model in models]

    async def count_live_connections(self, *, owner_username: str, pending_since: datetime) -> int:
        count = await self.session.scalar(
            select(func.count(TelegramConnectionModel.id)).where(
                TelegramConnectionModel.owner_username == owner_username,
                or_(
                    TelegramConnectionModel.state == TelegramConnectionState.ACTIVE,
                    and_(
                        TelegramConnectionModel.state == TelegramConnectionState.PENDING,
                        TelegramConnectionModel.requested_at > pending_since,
                    ),
                ),
            ),
        )
        return count or 0

    async def get_connection(self, *, connection_id: str) -> TelegramConnection | None:
        model = await self.session.scalar(
            select(TelegramConnectionModel)
            .where(
                TelegramConnectionModel.id == connection_id,
            )
            .with_for_update(),
        )
        return model.to_domain_schema() if model is not None else None

    async def get_connection_for_user(
        self,
        *,
        owner_username: str,
        telegram_user_id: int,
    ) -> TelegramConnection | None:
        model = await self.session.scalar(
            select(TelegramConnectionModel)
            .where(
                TelegramConnectionModel.owner_username == owner_username,
                TelegramConnectionModel.telegram_user_id == telegram_user_id,
                TelegramConnectionModel.state.in_(
                    [
                        TelegramConnectionState.PENDING,
                        TelegramConnectionState.ACTIVE,
                        TelegramConnectionState.BLOCKED,
                    ],
                ),
            )
            .with_for_update(),
        )
        return model.to_domain_schema() if model is not None else None

    async def has_active_connection(self, *, telegram_user_id: int) -> bool:
        value = await self.session.scalar(
            select(TelegramConnectionModel.id)
            .where(
                TelegramConnectionModel.telegram_user_id == telegram_user_id,
                TelegramConnectionModel.state == TelegramConnectionState.ACTIVE,
            )
            .limit(1),
        )
        return value is not None

    async def create_pending_connection(
        self,
        *,
        owner_username: str,
        participant: TelegramParticipant,
        label: str,
        now: datetime,
    ) -> TelegramConnection:
        model = TelegramConnectionModel(
            owner_username=owner_username,
            telegram_user_id=participant.user_id,
            private_chat_id=participant.private_chat_id,
            label=label,
            first_name=participant.first_name,
            username=participant.username,
            state=TelegramConnectionState.PENDING,
            requested_at=now,
            connected_at=None,
            state_changed_at=now,
            last_contact_at=now,
        )
        self.session.add(model)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            raise TelegramAccessError from exc
        return model.to_domain_schema()

    async def set_connection_state(
        self,
        *,
        connection_id: str,
        state: TelegramConnectionState,
        now: datetime,
    ) -> TelegramConnection:
        values: dict[str, object] = {"state": state, "state_changed_at": now}
        if state == TelegramConnectionState.ACTIVE:
            values["connected_at"] = now
        try:
            model = await self.session.scalar(
                update(TelegramConnectionModel)
                .where(
                    TelegramConnectionModel.id == connection_id,
                )
                .values(**values)
                .returning(TelegramConnectionModel),
            )
        except IntegrityError as exc:
            raise TelegramAccessError from exc
        if model is None:
            raise TelegramAccessError
        return model.to_domain_schema()

    async def set_connection_label(self, *, connection_id: str, label: str) -> TelegramConnection:
        model = await self.session.scalar(
            update(TelegramConnectionModel)
            .where(
                TelegramConnectionModel.id == connection_id,
            )
            .values(label=label)
            .returning(TelegramConnectionModel),
        )
        if model is None:
            raise TelegramAccessError
        return model.to_domain_schema()
