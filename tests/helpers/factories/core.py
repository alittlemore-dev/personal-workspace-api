import hashlib
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, Mock
from zoneinfo import ZoneInfo

from core.account_time_zone.clients import AccountTimeZoneReader
from core.cache_tools.enums import CacheWarmOperationStatusEnum
from core.cache_tools.schemas import CacheToolsStatus, CacheWarmOperation, CacheWarmSummary
from core.calendar.enums import CalendarEntryKind, CalendarEntryPeriod, CalendarWindow
from core.calendar.schemas import (
    Calendar,
    CalendarAnnualDate,
    CalendarEntry,
    CalendarRelatedPerson,
    CalendarSummary,
)
from core.events.enums import EventFrequency
from core.events.schemas import Event, EventDraft, EventRecurrence
from core.files.enums import FilePurpose
from core.files.schemas import FileRead, StoredFile
from core.files.types import Namespace
from core.finance.clients import FinanceRateClient
from core.finance.enums import FinanceCurrency, FinanceKind, FinanceRevisionAction, FinanceSource
from core.finance.exceptions import FinanceRateUnavailableError
from core.finance.schemas import (
    Amount,
    FinanceCategory,
    FinanceCategoryName,
    FinanceEventConfig,
    FinanceMonth,
    FinanceRateSet,
    FinanceRevisions,
    FinanceTransaction,
    FinanceTransactionDraft,
    FinanceTransactionPricing,
    FinanceTransactionRevision,
    FinanceTransactions,
    FinanceTransactionSnapshot,
)
from core.finance.services import (
    FinanceEventService,
    FinanceMonthService,
    FinanceStatisticsService,
    FinanceTelegramAccessService,
)
from core.finance.storages import FinanceStorage
from core.finance.use_cases import FinanceUseCase
from core.i18n.enums import LanguageEnum
from core.knowledge.dates.schemas import KnowledgeDate, KnowledgeDateDetails, KnowledgeDateValue
from core.knowledge.items.enums import KnowledgeItemKind
from core.knowledge.items.schemas import KnowledgeItem
from core.knowledge.people.schemas import (
    Person,
    PersonDetails,
    PersonRelationship,
    PersonRelationshipType,
)
from core.notifications.enums import ReminderKind
from core.notifications.schemas import ReminderRecipient, ReminderSource
from core.resumes.enums import ResumeCurrentStatusEnum
from core.resumes.schemas import (
    Resume,
    ResumeAdditionalSection,
    ResumeAdditionalSectionItem,
    ResumeCertificationItem,
    ResumeContent,
    ResumeEducationItem,
    ResumeExperienceItem,
    ResumeLanguageItem,
    ResumeProfile,
    ResumeProjectItem,
    Resumes,
    ResumeSkillGroup,
    ResumeSummary,
)
from core.telegram.enums import TelegramConnectionState
from core.telegram.schemas import TelegramConnection
from core.types import SearchName
from infra.postgresql.storages.finance import FinanceDatabaseStorage
from infra.postgresql.storages.finance_notifications import FinanceDatabaseEventDispatcher


class CoreFactoryHelper:
    @classmethod
    def knowledge_item(
        cls,
        *,
        item_id: str,
        display_name: str,
        kind: KnowledgeItemKind = KnowledgeItemKind.PERSON,
        author_username: str = "owner",
        now: datetime = datetime(2026, 7, 27, 12, tzinfo=UTC),
    ) -> KnowledgeItem:
        return KnowledgeItem(
            id=item_id,
            kind=kind,
            author_username=author_username,
            display_name=display_name,
            description="",
            tags=[],
            created_at=now,
            updated_at=now,
        )

    @classmethod
    def person_details(
        cls,
        *,
        item_id: str,
        last_name: str = "Иванов",
        first_name: str = "Иван",
        telegram: str = "",
    ) -> PersonDetails:
        return PersonDetails(
            item_id=item_id,
            last_name=last_name,
            first_name=first_name,
            middle_name="",
            email="",
            phone="",
            telegram=telegram,
            birthday=None,
            notifications_enabled=True,
        )

    @classmethod
    def person_relationship_type(
        cls,
        *,
        relationship_type_id: str,
        now: datetime = datetime(2026, 7, 27, 12, tzinfo=UTC),
    ) -> PersonRelationshipType:
        return PersonRelationshipType(
            id=relationship_type_id,
            author_username="owner",
            is_symmetric=False,
            forward_name="руководитель",
            reverse_name="подчинённый",
            created_at=now,
            updated_at=now,
        )

    @classmethod
    def person_relationship(
        cls,
        *,
        relationship_id: str,
        source_person_id: str,
        target_person_id: str,
        type_schema: PersonRelationshipType,
        now: datetime = datetime(2026, 7, 27, 12, tzinfo=UTC),
    ) -> PersonRelationship:
        return PersonRelationship(
            id=relationship_id,
            author_username="owner",
            source_person_id=source_person_id,
            target_person_id=target_person_id,
            relationship_type=type_schema,
            note="",
            created_at=now,
            updated_at=now,
        )

    @classmethod
    def knowledge_date(
        cls,
        *,
        date_id: str = "1" * 32,
        now: datetime = datetime(2026, 7, 30, 12, tzinfo=UTC),
    ) -> KnowledgeDate:
        return KnowledgeDate(
            item=cls.knowledge_item(
                item_id=date_id,
                kind=KnowledgeItemKind.DATE,
                author_username="test",
                display_name="Anniversary",
                now=now,
            ),
            details=KnowledgeDateDetails(
                item_id=date_id,
                date=KnowledgeDateValue(day=29, month=2, year=None),
                notifications_enabled=True,
            ),
            related_people=[],
            attachments=[],
        )

    @classmethod
    def person(
        cls,
        *,
        person_id: str = "1" * 32,
        now: datetime = datetime(2026, 7, 27, 12, tzinfo=UTC),
    ) -> Person:
        return Person(
            item=cls.knowledge_item(
                item_id=person_id,
                author_username="test",
                display_name="Ivanov Ivan",
                now=now,
            ),
            details=cls.person_details(
                item_id=person_id,
                last_name="Ivanov",
                first_name="Ivan",
            ),
            relationships=[],
            related_dates=[],
            photo=None,
            attachments=[],
        )

    @classmethod
    def event(
        cls,
        *,
        start: date | datetime,
        end: date | datetime,
        frequency: EventFrequency,
        until_date: date | None,
        all_day: bool,
        time_zone: str,
    ) -> Event:
        return Event.from_draft(
            event_id="a" * 32,
            draft=EventDraft(
                title="Meeting",
                description="",
                anchor_time_zone=ZoneInfo(time_zone),
                all_day=all_day,
                start=start,
                end=end,
                recurrence=EventRecurrence(frequency=frequency, until_date=until_date),
            ),
        )

    @classmethod
    def reminder_recipient(cls, *, notify_birthday: bool = True) -> ReminderRecipient:
        return ReminderRecipient(
            connection_id="c" * 32,
            owner_username="owner",
            private_chat_id=42,
            notify_birthday=notify_birthday,
            notify_memorable_date=False,
            language=LanguageEnum.RU,
        )

    @classmethod
    def reminder_source(cls) -> ReminderSource:
        return ReminderSource(
            owner_username="owner",
            item_id="i" * 32,
            kind=ReminderKind.BIRTHDAY,
            title="Анна",
            day=1,
            month=1,
            year=2000,
            description="",
            related_people=(),
            notifications_enabled=True,
        )

    @classmethod
    def calendar(cls) -> Calendar:
        return Calendar(
            reference_date=date(2026, 7, 31),
            window=CalendarWindow.CURRENT_AND_NEXT_MONTHS,
            summary=CalendarSummary(memorable_date_count=1, birthday_count=0),
            entries=[
                CalendarEntry(
                    id="1" * 32,
                    kind=CalendarEntryKind.MEMORABLE_DATE,
                    display_name="Годовщина",
                    annual_date=CalendarAnnualDate(day=2, month=8, year=2020),
                    period=CalendarEntryPeriod.NEXT_MONTH,
                    occurrence_year=2026,
                    related_people=[CalendarRelatedPerson(id="2" * 32, display_name="Анна")],
                ),
            ],
        )

    @classmethod
    def cache_tools_status(
        cls,
        *,
        queued_at: datetime = datetime(2026, 7, 16, 12, tzinfo=UTC),
    ) -> CacheToolsStatus:
        return CacheToolsStatus(
            enabled=True,
            configured_ttl_seconds=86_400,
            scheduled_warm_interval_seconds=3_600,
            domains=(),
            last_manual_warm_operation=CacheWarmOperation(
                operation_id="previous-operation",
                status=CacheWarmOperationStatusEnum.SUCCEEDED,
                queued_at=queued_at,
                summary=CacheWarmSummary(attempted=3, written=3, skipped=0),
            ),
        )

    @classmethod
    def finance_use_case(
        cls,
        storage: FinanceStorage,
        rate_client: FinanceRateClient | None = None,
    ) -> FinanceUseCase:
        if rate_client is None:
            client = Mock(spec=FinanceRateClient)
            client.fetch = AsyncMock(side_effect=FinanceRateUnavailableError)
            rate_client = client
        return FinanceUseCase(
            statistics_service=FinanceStatisticsService(),
            storage=storage,
            months=FinanceMonthService(
                storage=storage,
                time_zone_reader=AsyncMock(
                    spec=AccountTimeZoneReader,
                    get_time_zone=AsyncMock(return_value=ZoneInfo("UTC")),
                ),
            ),
            rate_client=rate_client,
            telegram_access=Mock(spec=FinanceTelegramAccessService),
            events=FinanceEventService(
                dispatcher=FinanceDatabaseEventDispatcher(session=storage.session),
                config=FinanceEventConfig(lifetime=timedelta(days=1)),
            )
            if isinstance(storage, FinanceDatabaseStorage)
            else Mock(spec=FinanceEventService),
        )

    @classmethod
    def finance_rate_set(cls, on_date: date = date(2026, 9, 15)) -> FinanceRateSet:
        return FinanceRateSet(
            effective_on=on_date,
            fetched_at=datetime.combine(on_date, datetime.min.time(), tzinfo=UTC),
            rates={
                FinanceCurrency.AMD: Decimal("0.2"),
                FinanceCurrency.RUB: Decimal(1),
                FinanceCurrency.USD: Decimal(80),
                FinanceCurrency.EUR: Decimal(90),
            },
            nominals={
                FinanceCurrency.AMD: 100,
                FinanceCurrency.RUB: 1,
                FinanceCurrency.USD: 1,
                FinanceCurrency.EUR: 1,
            },
            payload_hash=f"hash-{on_date.isoformat()}",
        )

    @classmethod
    def finance_transaction_draft(
        cls,
        category_id: str = "category",
        amount: str | Decimal = "10",
        currency: FinanceCurrency = FinanceCurrency.USD,
        occurred_at: datetime = datetime(2026, 9, 15, 12, tzinfo=UTC),
        description: str = "Meal",
    ) -> FinanceTransactionDraft:
        return FinanceTransactionDraft(
            category_id=category_id,
            amount=Amount(amount),
            currency=currency,
            occurred_at=occurred_at,
            description=description,
        )

    @classmethod
    def finance_category(
        cls,
        category_id: str = "category",
        stable_id: str = "stable-category",
        kind: FinanceKind = FinanceKind.EXPENSE,
        name: str = "Food",
        planned_amount: str | Decimal | None = None,
        actual_amount: str | Decimal = "0",
        difference: str | Decimal | None = None,
        position: int = 0,
        archived: bool = False,
    ) -> FinanceCategory:
        return FinanceCategory(
            id=category_id,
            stable_id=stable_id,
            kind=kind,
            name=FinanceCategoryName(name),
            planned_amount=Amount(planned_amount) if planned_amount is not None else None,
            actual_amount=Amount(actual_amount),
            difference=Amount(difference) if difference is not None else None,
            position=position,
            archived=archived,
        )

    @classmethod
    def finance_month(
        cls,
        month_id: str = "month",
        tracker_id: str = "tracker",
        period_start: date = date(2026, 9, 1),
        time_zone: ZoneInfo = ZoneInfo("UTC"),
        currency: FinanceCurrency = FinanceCurrency.USD,
        opening_balance: str | Decimal = "0",
        actual_income: str | Decimal = "0",
        actual_expense: str | Decimal = "10",
        planned_income: str | Decimal | None = None,
        planned_expense: str | Decimal | None = None,
        closing_balance: str | Decimal = "-10",
        categories: list[FinanceCategory] | None = None,
    ) -> FinanceMonth:
        return FinanceMonth(
            id=month_id,
            tracker_id=tracker_id,
            period_start=period_start,
            time_zone=time_zone,
            currency=currency,
            opening_balance=Amount(opening_balance),
            actual_income=Amount(actual_income),
            actual_expense=Amount(actual_expense),
            planned_income=Amount(planned_income) if planned_income is not None else None,
            planned_expense=Amount(planned_expense) if planned_expense is not None else None,
            closing_balance=Amount(closing_balance),
            categories=categories if categories is not None else [],
        )

    @classmethod
    def finance_transaction(
        cls,
        transaction_id: str = "transaction",
        category_id: str | None = "category",
        category_name: str = "Food",
        kind: FinanceKind = FinanceKind.EXPENSE,
        amount: str | Decimal = "10",
        currency: FinanceCurrency = FinanceCurrency.USD,
        converted_amount: str | Decimal = "10",
        occurred_at: datetime = datetime(2026, 9, 15, 12, tzinfo=UTC),
        description: str = "Meal",
        rate_effective_on: date = date(2026, 9, 15),
        version: int = 1,
        deleted: bool = False,
        pricing: FinanceTransactionPricing | None = None,
    ) -> FinanceTransaction:
        return FinanceTransaction(
            created_at=datetime(2026, 9, 15, tzinfo=UTC),
            id=transaction_id,
            category_id=category_id,
            category_name=category_name,
            kind=kind,
            amount=Amount(amount),
            currency=currency,
            converted_amount=Amount(converted_amount),
            occurred_at=occurred_at,
            description=description,
            rate_effective_on=rate_effective_on,
            version=version,
            deleted=deleted,
            pricing=pricing
            if pricing is not None
            else FinanceTransactionPricing(
                rate_set_id="rate-set",
                amount_rub=Amount(Amount(amount) * cls.finance_rate_set().rates[currency]),
            ),
            source=FinanceSource.WEB,
            author_id="owner",
            author_label="owner",
        )

    @classmethod
    def finance_transaction_revision(
        cls,
        number: int = 1,
        action: FinanceRevisionAction = FinanceRevisionAction.UPDATE,
        previous_state: FinanceTransactionSnapshot | None = None,
        actor_username: str = "owner",
        changed_at: datetime = datetime(2026, 9, 15, 12, tzinfo=UTC),
    ) -> FinanceTransactionRevision:
        return FinanceTransactionRevision(
            number=number,
            action=action,
            previous_state=previous_state
            if previous_state is not None
            else {
                "categoryId": "category",
                "kind": "expense",
                "amount": "10",
                "currency": "USD",
                "amountRub": "800",
                "rateSetId": "rate-set",
                "occurredAt": changed_at.isoformat(),
                "description": "Meal",
                "version": number,
                "deleted": False,
            },
            actor_username=actor_username,
            changed_at=changed_at,
        )

    @classmethod
    def finance_transactions(
        cls,
        transactions: list[FinanceTransaction] | None = None,
    ) -> FinanceTransactions:
        return FinanceTransactions(transactions=transactions if transactions is not None else [])

    @classmethod
    def finance_revisions(
        cls,
        revisions: list[FinanceTransactionRevision] | None = None,
    ) -> FinanceRevisions:
        return FinanceRevisions(revisions=revisions if revisions is not None else [])

    @classmethod
    def hex_id(cls, value: int | str = 1) -> str:
        if isinstance(value, str):
            return value
        return f"{value % (1 << 128):032x}"

    @classmethod
    def hex_id_from_text(cls, value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()[:32]

    @classmethod
    def resume_content(
        cls,
        full_name: str = "Candidate Name",
        role: str = "Инженер",
        summary: str = "Короткое описание опыта.",
        skills: list[ResumeSkillGroup] | None = None,
        experience: list[ResumeExperienceItem] | None = None,
    ) -> ResumeContent:
        return ResumeContent(
            profile=ResumeProfile(
                full_name=full_name,
                photo_file_id="",
                role=role,
                location="",
                email="",
                phone="",
                website_url="",
                linkedin_url="",
                github_url="",
                telegram="",
            ),
            summary=ResumeSummary(text=summary),
            skills=skills
            if skills is not None
            else [ResumeSkillGroup(category="Backend", items=["Python", "PostgreSQL"])],
            experience=experience if experience is not None else [],
            education=[],
            languages=[],
            certifications=[],
            additional_sections=[],
        )

    @classmethod
    def resume_empty_content(cls, summary: str = "") -> ResumeContent:
        return ResumeContent(
            profile=ResumeProfile(
                full_name="",
                photo_file_id="",
                role="",
                location="",
                email="",
                phone="",
                website_url="",
                linkedin_url="",
                github_url="",
                telegram="",
            ),
            summary=ResumeSummary(text=summary),
            skills=[],
            experience=[],
            education=[],
            languages=[],
            certifications=[],
            additional_sections=[],
        )

    @classmethod
    def resume_full_content(
        cls,
        summary: str = "Builds reliable backend systems.",
        skill_items: list[str] | None = None,
    ) -> ResumeContent:
        return ResumeContent(
            profile=ResumeProfile(
                full_name="Dmitriy Ivanov",
                photo_file_id="",
                role="Backend engineer",
                location="Moscow",
                email="dmitriy@example.com",
                phone="+79990000000",
                website_url="https://example.com",
                linkedin_url="https://linkedin.com/in/dmitriy",
                github_url="https://github.com/dmitriy",
                telegram="@dmitriy",
            ),
            summary=ResumeSummary(text=summary),
            skills=[
                ResumeSkillGroup(
                    category="Languages",
                    items=skill_items if skill_items is not None else ["Python", "TypeScript"],
                ),
            ],
            experience=[
                ResumeExperienceItem(
                    company="Company",
                    company_website_url="https://company.example",
                    position="Engineer",
                    location="Moscow",
                    start_date=date(2023, 1, 1),
                    end_date=None,
                    current_status=ResumeCurrentStatusEnum.CURRENT,
                    summary="Built platform services.",
                    highlights=["Reduced response time"],
                    technologies=["Python", "PostgreSQL"],
                    projects=[
                        ResumeProjectItem(
                            name="Portfolio",
                            role="Creator",
                            team_size="6 engineers",
                            scale="2M requests/day",
                            description="Site and knowledge base",
                            highlights=["Angular CSR"],
                            technologies=["Litestar", "Angular"],
                            url="https://example.com",
                        ),
                    ],
                ),
            ],
            education=[
                ResumeEducationItem(
                    institution="University",
                    degree="Bachelor",
                    field="Computer science",
                    location="Moscow",
                    start_date=date(2014, 9, 1),
                    end_date=date(2018, 6, 30),
                    description="Applied computer science",
                ),
            ],
            languages=[ResumeLanguageItem(name="English", proficiency="C1")],
            certifications=[
                ResumeCertificationItem(
                    name="Certificate",
                    issuer="Provider",
                    issued_on=date(2025, 1, 1),
                    expires_on=None,
                    credential_url="https://example.com/cert",
                ),
            ],
            additional_sections=[
                ResumeAdditionalSection(
                    title="Publications",
                    items=[
                        ResumeAdditionalSectionItem(
                            title="Article",
                            description="Technical write-up",
                            url="https://example.com/article",
                        ),
                    ],
                ),
            ],
        )

    @classmethod
    def resume(
        cls,
        resume_id: int | str = 1,
        title: str = "Backend resume",
        language: LanguageEnum = LanguageEnum.RU,
        content: ResumeContent | None = None,
        author_username: str = "test",
        created_at: str | None = None,
        updated_at: str | None = None,
    ) -> Resume:
        now = datetime.now(tz=UTC)
        return Resume(
            id=cls.hex_id(resume_id),
            title=title,
            language=language,
            content=content or cls.resume_content(),
            author_username=author_username,
            created_at=datetime.fromisoformat(created_at).replace(tzinfo=UTC)
            if created_at is not None
            else now,
            updated_at=datetime.fromisoformat(updated_at).replace(tzinfo=UTC)
            if updated_at is not None
            else now,
        )

    @classmethod
    def resumes(
        cls,
        values: list[Resume] | None = None,
        total_count: int = 0,
        total_pages: int = 0,
    ) -> Resumes:
        return Resumes(values=values or [], total_count=total_count, total_pages=total_pages)

    @classmethod
    def stored_file(
        cls,
        file_id: int | str = 1,
        purpose: FilePurpose = FilePurpose.ATTACHMENT,
        namespace: Namespace = "media",
        relative_path: str = "attachments/file.png",
        mime_type: str = "image/png",
        size_bytes: int = 4,
        name: str = "Attachment",
        original_name: str = "original.png",
        original_sha256: str | None = None,
        orphaned_at: datetime | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> StoredFile:
        now = datetime(2026, 7, 3, 10, 0, tzinfo=UTC)
        return StoredFile(
            id=cls.hex_id(file_id) if isinstance(file_id, int) else file_id,
            purpose=purpose,
            namespace=namespace,
            relative_path=relative_path,
            mime_type=mime_type,
            size_bytes=size_bytes,
            name=name,
            original_name=original_name,
            original_sha256=original_sha256,
            orphaned_at=orphaned_at,
            created_at=created_at or now,
            updated_at=updated_at or now,
        )

    @classmethod
    def file_read(
        cls,
        file: StoredFile | None = None,
        access_url: str = "https://cdn.example.test/media/attachments/file.png",
        markdown_url: str = "https://cdn.example.test/media/attachments/file.png#fileId=00000000000000000000000000000001",
    ) -> FileRead:
        return FileRead(
            file=file or cls.stored_file(),
            access_url=access_url,
            markdown_url=markdown_url,
        )

    @classmethod
    def stored_pdf(
        cls,
        *,
        file_id: str = "file-id",
        purpose: FilePurpose = FilePurpose.ATTACHMENT,
        orphaned_at: datetime | None = datetime(2026, 7, 3, 10, tzinfo=UTC),
    ) -> StoredFile:
        return cls.stored_file(
            file_id=file_id,
            purpose=purpose,
            relative_path=f"attachments/{file_id}.pdf",
            mime_type="application/pdf",
            original_name="original.pdf",
            original_sha256=hashlib.sha256(b"data").hexdigest(),
            orphaned_at=orphaned_at,
        )

    @classmethod
    def search_name(cls, value: Any) -> SearchName:
        return SearchName(value)

    @classmethod
    def telegram_connection(
        cls,
        *,
        owner_username: str = "owner",
        telegram_user_id: int = 42,
        connection_id: str = "c" * 32,
        notify_finance_transaction: bool = True,
        notify_finance_limit: bool = True,
    ) -> TelegramConnection:
        now = datetime(2026, 9, 15, 12, tzinfo=UTC)
        return TelegramConnection(
            id=connection_id,
            owner_username=owner_username,
            telegram_user_id=telegram_user_id,
            private_chat_id=telegram_user_id,
            label="Family",
            first_name="Boris",
            username="boris",
            state=TelegramConnectionState.ACTIVE,
            requested_at=now,
            connected_at=now,
            last_contact_at=now,
            notify_birthday=False,
            notify_memorable_date=False,
            notify_finance_transaction=notify_finance_transaction,
            notify_finance_limit=notify_finance_limit,
            language=LanguageEnum.RU,
        )
