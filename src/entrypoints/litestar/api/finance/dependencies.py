from datetime import date, datetime

from backend_sdk import Principal
from backend_sdk.integrations.litestar import AuthContext
from dishka import FromDishka
from dishka.integrations.litestar import inject
from litestar import Request
from litestar.datastructures import State
from litestar.di import NamedDependency
from litestar.params import FromPath, FromQuery

from core.account_time_zone.clients import AccountTimeZoneReader
from core.finance.enums import (
    FinanceStatisticsCurrency,
    FinanceStatisticsPeriod,
)
from core.finance.exceptions import InvalidFinanceDataError
from core.finance.schemas import (
    Amount,
    ChangeFinanceCurrencyParams,
    CreateFinanceCategoryParams,
    CreateFinanceTransactionParams,
    DeleteFinanceCategoryParams,
    EnsureFinanceMonthParams,
    FinanceActor,
    FinanceCategoryName,
    FinanceHistoricalMonthParams,
    FinanceMonthParams,
    FinanceStatisticsParams,
    FinanceTransactionRevisionsParams,
    HistoricalFinanceRevisionsParams,
    ListFinanceTransactionsParams,
    ListHistoricalFinanceTransactionsParams,
    SetFinanceCategoryArchivedParams,
    SetFinanceTransactionDeletedParams,
    UpdateFinanceCategoryParams,
    UpdateFinanceTransactionParams,
    UpdateOpeningBalanceParams,
)
from entrypoints.litestar.api.finance.schemas import (
    ChangeMonthCurrencyRequest,
    CreateFinanceCategoryRequest,
    EnsureFinanceMonthRequest,
    FinanceTransactionRequest,
    FinanceTransactionUpdateRequest,
    FinanceVersionRequest,
    OpeningBalanceRequest,
    UpdateFinanceCategoryRequest,
)


@inject
async def provide_finance_context(
    request: Request[Principal, AuthContext, State],
    current_datetime: FromDishka[datetime],
) -> FinanceMonthParams:
    return FinanceMonthParams(owner_username=request.user.username, now=current_datetime)


@inject
async def provide_ensure_month_params(
    data: EnsureFinanceMonthRequest,
    month_context: NamedDependency[FinanceMonthParams],
    time_zone_reader: FromDishka[AccountTimeZoneReader],
) -> EnsureFinanceMonthParams:
    return EnsureFinanceMonthParams(
        owner_username=month_context.owner_username,
        now=month_context.now,
        time_zone=await time_zone_reader.get_time_zone(owner_username=month_context.owner_username),
        language=data.language,
    )


def provide_opening_balance_params(
    data: OpeningBalanceRequest,
    month_context: NamedDependency[FinanceMonthParams],
) -> UpdateOpeningBalanceParams:
    return UpdateOpeningBalanceParams(
        owner_username=month_context.owner_username,
        now=month_context.now,
        amount=Amount(data.amount),
    )


def provide_currency_change_params(
    data: ChangeMonthCurrencyRequest,
    month_context: NamedDependency[FinanceMonthParams],
) -> ChangeFinanceCurrencyParams:
    return ChangeFinanceCurrencyParams(
        owner_username=month_context.owner_username,
        now=month_context.now,
        currency=data.currency,
    )


def provide_create_category_params(
    data: CreateFinanceCategoryRequest,
    month_context: NamedDependency[FinanceMonthParams],
) -> CreateFinanceCategoryParams:
    return CreateFinanceCategoryParams(
        owner_username=month_context.owner_username,
        now=month_context.now,
        kind=data.kind,
        name=FinanceCategoryName(data.name),
        planned_amount=Amount(data.planned_amount) if data.planned_amount is not None else None,
    )


def provide_update_category_params(
    category_id: FromPath[str],
    data: UpdateFinanceCategoryRequest,
    month_context: NamedDependency[FinanceMonthParams],
) -> UpdateFinanceCategoryParams:
    return UpdateFinanceCategoryParams(
        owner_username=month_context.owner_username,
        now=month_context.now,
        category_id=category_id,
        name=FinanceCategoryName(data.name),
        planned_amount=Amount(data.planned_amount) if data.planned_amount is not None else None,
        position=data.position,
    )


def provide_archive_category_params(
    category_id: FromPath[str],
    month_context: NamedDependency[FinanceMonthParams],
) -> SetFinanceCategoryArchivedParams:
    return SetFinanceCategoryArchivedParams(
        owner_username=month_context.owner_username,
        now=month_context.now,
        category_id=category_id,
        archived=True,
    )


def provide_restore_category_params(
    category_id: FromPath[str],
    month_context: NamedDependency[FinanceMonthParams],
) -> SetFinanceCategoryArchivedParams:
    return SetFinanceCategoryArchivedParams(
        owner_username=month_context.owner_username,
        now=month_context.now,
        category_id=category_id,
        archived=False,
    )


def provide_delete_category_params(
    category_id: FromPath[str],
    month_context: NamedDependency[FinanceMonthParams],
) -> DeleteFinanceCategoryParams:
    return DeleteFinanceCategoryParams(
        owner_username=month_context.owner_username,
        now=month_context.now,
        category_id=category_id,
    )


def provide_list_transactions_params(
    include_deleted: FromQuery[bool],
    month_context: NamedDependency[FinanceMonthParams],
) -> ListFinanceTransactionsParams:
    return ListFinanceTransactionsParams(
        owner_username=month_context.owner_username,
        now=month_context.now,
        include_deleted=include_deleted,
    )


def provide_create_transaction_params(
    data: FinanceTransactionRequest,
    month_context: NamedDependency[FinanceMonthParams],
) -> CreateFinanceTransactionParams:
    return CreateFinanceTransactionParams(
        period_start=None,
        owner_username=month_context.owner_username,
        now=month_context.now,
        draft=data.to_domain_schema(),
        actor=FinanceActor.web(month_context.owner_username),
    )


def provide_update_transaction_params(
    transaction_id: FromPath[str],
    data: FinanceTransactionUpdateRequest,
    month_context: NamedDependency[FinanceMonthParams],
) -> UpdateFinanceTransactionParams:
    return UpdateFinanceTransactionParams(
        period_start=None,
        owner_username=month_context.owner_username,
        now=month_context.now,
        transaction_id=transaction_id,
        draft=data.to_domain_schema(),
        version=data.version,
    )


def provide_delete_transaction_params(
    transaction_id: FromPath[str],
    version: FromQuery[int],
    month_context: NamedDependency[FinanceMonthParams],
) -> SetFinanceTransactionDeletedParams:
    return SetFinanceTransactionDeletedParams(
        period_start=None,
        owner_username=month_context.owner_username,
        now=month_context.now,
        transaction_id=transaction_id,
        version=version,
        deleted=True,
    )


def provide_restore_transaction_params(
    transaction_id: FromPath[str],
    data: FinanceVersionRequest,
    month_context: NamedDependency[FinanceMonthParams],
) -> SetFinanceTransactionDeletedParams:
    return SetFinanceTransactionDeletedParams(
        period_start=None,
        owner_username=month_context.owner_username,
        now=month_context.now,
        transaction_id=transaction_id,
        version=data.version,
        deleted=False,
    )


def provide_transaction_revisions_params(
    transaction_id: FromPath[str],
    month_context: NamedDependency[FinanceMonthParams],
) -> FinanceTransactionRevisionsParams:
    return FinanceTransactionRevisionsParams(
        owner_username=month_context.owner_username,
        now=month_context.now,
        transaction_id=transaction_id,
    )


def provide_historical_context(
    year: FromPath[int],
    month: FromPath[int],
    month_context: NamedDependency[FinanceMonthParams],
) -> FinanceHistoricalMonthParams:
    try:
        period_start = date(year, month, 1)
    except ValueError as error:
        raise InvalidFinanceDataError from error
    return FinanceHistoricalMonthParams(
        owner_username=month_context.owner_username,
        now=month_context.now,
        period_start=period_start,
    )


def provide_historical_transactions_params(
    historical_context: NamedDependency[FinanceHistoricalMonthParams],
    include_deleted: FromQuery[bool],
) -> ListHistoricalFinanceTransactionsParams:
    return ListHistoricalFinanceTransactionsParams(
        owner_username=historical_context.owner_username,
        now=historical_context.now,
        period_start=historical_context.period_start,
        include_deleted=include_deleted,
    )


def provide_historical_revisions_params(
    historical_context: NamedDependency[FinanceHistoricalMonthParams],
    transaction_id: FromPath[str],
) -> HistoricalFinanceRevisionsParams:
    return HistoricalFinanceRevisionsParams(
        owner_username=historical_context.owner_username,
        now=historical_context.now,
        period_start=historical_context.period_start,
        transaction_id=transaction_id,
    )


def provide_statistics_params(
    period: FromQuery[FinanceStatisticsPeriod],
    currency: FromQuery[str],
    month_context: NamedDependency[FinanceMonthParams],
) -> FinanceStatisticsParams:
    try:
        selected = FinanceStatisticsCurrency(currency)
    except ValueError as error:
        raise InvalidFinanceDataError from error
    return FinanceStatisticsParams(
        owner_username=month_context.owner_username,
        now=month_context.now,
        period=period,
        currency=selected,
    )


def provide_historical_create_transaction_params(
    data: FinanceTransactionRequest,
    historical_context: NamedDependency[FinanceHistoricalMonthParams],
) -> CreateFinanceTransactionParams:
    return CreateFinanceTransactionParams(
        period_start=historical_context.period_start,
        owner_username=historical_context.owner_username,
        now=historical_context.now,
        draft=data.to_domain_schema(),
        actor=FinanceActor.web(historical_context.owner_username),
    )


def provide_historical_update_transaction_params(
    transaction_id: FromPath[str],
    data: FinanceTransactionUpdateRequest,
    historical_context: NamedDependency[FinanceHistoricalMonthParams],
) -> UpdateFinanceTransactionParams:
    return UpdateFinanceTransactionParams(
        period_start=historical_context.period_start,
        owner_username=historical_context.owner_username,
        now=historical_context.now,
        transaction_id=transaction_id,
        draft=data.to_domain_schema(),
        version=data.version,
    )


def provide_historical_delete_transaction_params(
    transaction_id: FromPath[str],
    version: FromQuery[int],
    historical_context: NamedDependency[FinanceHistoricalMonthParams],
) -> SetFinanceTransactionDeletedParams:
    return SetFinanceTransactionDeletedParams(
        period_start=historical_context.period_start,
        owner_username=historical_context.owner_username,
        now=historical_context.now,
        transaction_id=transaction_id,
        version=version,
        deleted=True,
    )


def provide_historical_restore_transaction_params(
    transaction_id: FromPath[str],
    data: FinanceVersionRequest,
    historical_context: NamedDependency[FinanceHistoricalMonthParams],
) -> SetFinanceTransactionDeletedParams:
    return SetFinanceTransactionDeletedParams(
        period_start=historical_context.period_start,
        owner_username=historical_context.owner_username,
        now=historical_context.now,
        transaction_id=transaction_id,
        version=data.version,
        deleted=False,
    )
