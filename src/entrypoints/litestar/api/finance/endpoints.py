from dishka import FromDishka
from dishka.integrations.litestar import DishkaRouter
from litestar import Controller, delete, get, post, put, status_codes
from litestar.di import NamedDependency, Provide

from core.finance.schemas import (
    ChangeFinanceCurrencyParams,
    CreateFinanceCategoryParams,
    CreateFinanceTransactionParams,
    DeleteFinanceCategoryParams,
    EnsureFinanceMonthParams,
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
from core.finance.use_cases import FinanceUseCase
from entrypoints.litestar.api.finance.dependencies import (
    provide_archive_category_params,
    provide_create_category_params,
    provide_create_transaction_params,
    provide_currency_change_params,
    provide_delete_category_params,
    provide_delete_transaction_params,
    provide_ensure_month_params,
    provide_finance_context,
    provide_historical_context,
    provide_historical_create_transaction_params,
    provide_historical_delete_transaction_params,
    provide_historical_restore_transaction_params,
    provide_historical_revisions_params,
    provide_historical_transactions_params,
    provide_historical_update_transaction_params,
    provide_list_transactions_params,
    provide_opening_balance_params,
    provide_restore_category_params,
    provide_restore_transaction_params,
    provide_statistics_params,
    provide_transaction_revisions_params,
    provide_update_category_params,
    provide_update_transaction_params,
)
from entrypoints.litestar.api.finance.schemas import (
    FinanceMonthResponse,
    FinanceRevisionsResponse,
    FinanceStatisticsResultResponse,
    FinanceTransactionResponse,
    FinanceTransactionsResponse,
)
from infra.config.constants import constants


class FinanceApiController(Controller):
    path = "/finance"
    tags = ["finance"]
    dependencies = {"month_context": Provide(provide_finance_context)}
    response_headers = {
        constants.knowledge_files.cache_control_header_name: (
            constants.knowledge_files.no_store_header_value
        ),
    }

    @post(
        "/current-month/ensure",
        status_code=status_codes.HTTP_200_OK,
        dependencies={"params": Provide(provide_ensure_month_params)},
        opt={"pat_permissions": ("workspace.finance.update",), "error_statuses": (400, 503)},
        description=(
            "Initialize the current finance month if needed and return it. The "
            "account time zone defines month boundaries; language selects the "
            "initial currency and category labels.\n\nPersonal API token "
            "permissions: workspace.finance.update."
        ),
        summary="Ensure month",
    )
    async def ensure_month(
        self,
        use_case: FromDishka[FinanceUseCase],
        params: NamedDependency[EnsureFinanceMonthParams],
    ) -> FinanceMonthResponse:
        return FinanceMonthResponse.from_domain(await use_case.ensure_month(params))

    @get(
        "/current-month",
        status_code=status_codes.HTTP_200_OK,
        opt={"pat_permissions": ("workspace.finance.read",), "error_statuses": (404,)},
        description=(
            "Return the current finance month, its opening and closing balances, "
            "and categories. The month must first be initialized with POST "
            "/api/finance/current-month/ensure.\n\nPersonal API token permissions: "
            "workspace.finance.read."
        ),
        summary="Get month",
    )
    async def get_month(
        self,
        use_case: FromDishka[FinanceUseCase],
        month_context: NamedDependency[FinanceMonthParams],
    ) -> FinanceMonthResponse:
        return FinanceMonthResponse.from_domain(await use_case.get_month(month_context))

    @put(
        "/current-month/opening-balance",
        status_code=status_codes.HTTP_200_OK,
        dependencies={"params": Provide(provide_opening_balance_params, sync_to_thread=False)},
        opt={"pat_permissions": ("workspace.finance.update",), "error_statuses": (400, 404)},
        description=(
            "Replace the current month opening balance and return recalculated "
            "balances.\n\nPersonal API token permissions: workspace.finance.update."
        ),
        summary="Update opening balance",
    )
    async def update_opening_balance(
        self,
        use_case: FromDishka[FinanceUseCase],
        params: NamedDependency[UpdateOpeningBalanceParams],
    ) -> FinanceMonthResponse:
        return FinanceMonthResponse.from_domain(await use_case.update_opening_balance(params))

    @post(
        "/current-month/currency-changes",
        status_code=status_codes.HTTP_200_OK,
        dependencies={"params": Provide(provide_currency_change_params, sync_to_thread=False)},
        opt={"pat_permissions": ("workspace.finance.update",), "error_statuses": (400, 404, 503)},
        description=(
            "Change the current month currency and return the recalculated "
            "budget. Currency conversion requires an available exchange "
            "rate.\n\nPersonal API token permissions: workspace.finance.update."
        ),
        summary="Change currency",
    )
    async def change_currency(
        self,
        use_case: FromDishka[FinanceUseCase],
        params: NamedDependency[ChangeFinanceCurrencyParams],
    ) -> FinanceMonthResponse:
        return FinanceMonthResponse.from_domain(await use_case.change_currency(params))

    @post(
        "/current-month/categories",
        status_code=status_codes.HTTP_201_CREATED,
        dependencies={"params": Provide(provide_create_category_params, sync_to_thread=False)},
        opt={"pat_permissions": ("workspace.finance.create",), "error_statuses": (400, 404)},
        description=(
            "Create a category in the current month. kind selects income or "
            "expense; plannedAmount=null leaves the category without a spending "
            "or income plan.\n\nPersonal API token permissions: "
            "workspace.finance.create."
        ),
        summary="Create category",
    )
    async def create_category(
        self,
        use_case: FromDishka[FinanceUseCase],
        params: NamedDependency[CreateFinanceCategoryParams],
    ) -> FinanceMonthResponse:
        return FinanceMonthResponse.from_domain(await use_case.create_category(params))

    @put(
        "/current-month/categories/{category_id:str}",
        status_code=status_codes.HTTP_200_OK,
        dependencies={"params": Provide(provide_update_category_params, sync_to_thread=False)},
        opt={"pat_permissions": ("workspace.finance.update",), "error_statuses": (400, 404)},
        description=(
            "Replace the category name, plan, and display position in the "
            "current month.\n\nPersonal API token permissions: "
            "workspace.finance.update."
        ),
        summary="Update category",
    )
    async def update_category(
        self,
        use_case: FromDishka[FinanceUseCase],
        params: NamedDependency[UpdateFinanceCategoryParams],
    ) -> FinanceMonthResponse:
        return FinanceMonthResponse.from_domain(await use_case.update_category(params))

    @delete(
        "/current-month/categories/{category_id:str}",
        status_code=status_codes.HTTP_200_OK,
        dependencies={"params": Provide(provide_archive_category_params, sync_to_thread=False)},
        opt={"pat_permissions": ("workspace.finance.delete",), "error_statuses": (400, 404)},
        description=(
            "Archive a current month category. Its transaction history is "
            "retained.\n\nPersonal API token permissions: workspace.finance.delete."
        ),
        summary="Archive category",
    )
    async def archive_category(
        self,
        use_case: FromDishka[FinanceUseCase],
        params: NamedDependency[SetFinanceCategoryArchivedParams],
    ) -> FinanceMonthResponse:
        return FinanceMonthResponse.from_domain(await use_case.set_category_archived(params))

    @delete(
        "/current-month/categories/{category_id:str}/permanent",
        status_code=status_codes.HTTP_200_OK,
        dependencies={"params": Provide(provide_delete_category_params, sync_to_thread=False)},
        opt={"pat_permissions": ("workspace.finance.delete",), "error_statuses": (400, 404)},
        description=(
            "Permanently delete this stable category and its snapshots across "
            "all months. Transaction records are retained but become "
            "uncategorized. This also removes the category from historical month "
            "budgets.\n\nPersonal API token permissions: workspace.finance.delete."
        ),
        summary="Delete category",
    )
    async def delete_category(
        self,
        use_case: FromDishka[FinanceUseCase],
        params: NamedDependency[DeleteFinanceCategoryParams],
    ) -> FinanceMonthResponse:
        return FinanceMonthResponse.from_domain(await use_case.delete_category(params))

    @post(
        "/current-month/categories/{category_id:str}/restore",
        status_code=status_codes.HTTP_200_OK,
        dependencies={"params": Provide(provide_restore_category_params, sync_to_thread=False)},
        opt={"pat_permissions": ("workspace.finance.update",), "error_statuses": (400, 404)},
        description=(
            "Restore an archived current month category and return the updated "
            "month.\n\nPersonal API token permissions: workspace.finance.update."
        ),
        summary="Restore category",
    )
    async def restore_category(
        self,
        use_case: FromDishka[FinanceUseCase],
        params: NamedDependency[SetFinanceCategoryArchivedParams],
    ) -> FinanceMonthResponse:
        return FinanceMonthResponse.from_domain(await use_case.set_category_archived(params))

    @get(
        "/current-month/transactions",
        status_code=status_codes.HTTP_200_OK,
        dependencies={"params": Provide(provide_list_transactions_params, sync_to_thread=False)},
        opt={"pat_permissions": ("workspace.finance.read",), "error_statuses": ()},
        description=(
            "Return transactions for the current month. The required "
            "include_deleted query parameter controls whether soft-deleted "
            "entries are included. This list is not paginated.\n\nPersonal API "
            "token permissions: workspace.finance.read."
        ),
        summary="List transactions",
    )
    async def list_transactions(
        self,
        use_case: FromDishka[FinanceUseCase],
        params: NamedDependency[ListFinanceTransactionsParams],
    ) -> FinanceTransactionsResponse:
        return FinanceTransactionsResponse.from_domain(await use_case.list_transactions(params))

    @post(
        "/current-month/transactions",
        status_code=status_codes.HTTP_201_CREATED,
        dependencies={"params": Provide(provide_create_transaction_params, sync_to_thread=False)},
        opt={"pat_permissions": ("workspace.finance.create",), "error_statuses": (400, 404, 503)},
        description=(
            "Record a transaction in the current month. The amount must be "
            "positive and use the precision supported by currency; exchange "
            "rates convert it to the month currency.\n\nPersonal API token "
            "permissions: workspace.finance.create."
        ),
        summary="Create transaction",
    )
    async def create_transaction(
        self,
        use_case: FromDishka[FinanceUseCase],
        params: NamedDependency[CreateFinanceTransactionParams],
    ) -> FinanceTransactionResponse:
        return FinanceTransactionResponse.from_domain(await use_case.create_transaction(params))

    @put(
        "/current-month/transactions/{transaction_id:str}",
        status_code=status_codes.HTTP_200_OK,
        dependencies={"params": Provide(provide_update_transaction_params, sync_to_thread=False)},
        opt={
            "pat_permissions": ("workspace.finance.update",),
            "error_statuses": (400, 404, 409, 503),
        },
        description=(
            "Replace a current month transaction. Send its latest version; a "
            "stale version returns 409. A revision is retained.\n\nPersonal API "
            "token permissions: workspace.finance.update."
        ),
        summary="Update transaction",
    )
    async def update_transaction(
        self,
        use_case: FromDishka[FinanceUseCase],
        params: NamedDependency[UpdateFinanceTransactionParams],
    ) -> FinanceTransactionResponse:
        return FinanceTransactionResponse.from_domain(await use_case.update_transaction(params))

    @delete(
        "/current-month/transactions/{transaction_id:str}",
        status_code=status_codes.HTTP_200_OK,
        dependencies={"params": Provide(provide_delete_transaction_params, sync_to_thread=False)},
        opt={
            "pat_permissions": ("workspace.finance.delete",),
            "error_statuses": (400, 404, 409),
        },
        description=(
            "Soft-delete a current month transaction. The required version query "
            "parameter prevents overwriting a concurrent change; a revision is "
            "retained.\n\nPersonal API token permissions: workspace.finance.delete."
        ),
        summary="Delete transaction",
    )
    async def delete_transaction(
        self,
        use_case: FromDishka[FinanceUseCase],
        params: NamedDependency[SetFinanceTransactionDeletedParams],
    ) -> FinanceTransactionResponse:
        return FinanceTransactionResponse.from_domain(
            await use_case.set_transaction_deleted(params),
        )

    @post(
        "/current-month/transactions/{transaction_id:str}/restore",
        status_code=status_codes.HTTP_200_OK,
        dependencies={"params": Provide(provide_restore_transaction_params, sync_to_thread=False)},
        opt={
            "pat_permissions": ("workspace.finance.update",),
            "error_statuses": (400, 404, 409),
        },
        description=(
            "Restore a soft-deleted current month transaction using its latest "
            "version; a stale version returns 409.\n\nPersonal API token "
            "permissions: workspace.finance.update."
        ),
        summary="Restore transaction",
    )
    async def restore_transaction(
        self,
        use_case: FromDishka[FinanceUseCase],
        params: NamedDependency[SetFinanceTransactionDeletedParams],
    ) -> FinanceTransactionResponse:
        return FinanceTransactionResponse.from_domain(
            await use_case.set_transaction_deleted(params),
        )

    @get(
        "/current-month/transactions/{transaction_id:str}/revisions",
        status_code=status_codes.HTTP_200_OK,
        dependencies={
            "params": Provide(provide_transaction_revisions_params, sync_to_thread=False),
        },
        opt={"pat_permissions": ("workspace.finance.read",), "error_statuses": (404,)},
        description=(
            "Return the ordered revision history of a current month transaction, "
            "including previous states and the actor of each change.\n\nPersonal "
            "API token permissions: workspace.finance.read."
        ),
        summary="Transaction revisions",
    )
    async def transaction_revisions(
        self,
        use_case: FromDishka[FinanceUseCase],
        params: NamedDependency[FinanceTransactionRevisionsParams],
    ) -> FinanceRevisionsResponse:
        return FinanceRevisionsResponse.from_domain(await use_case.revisions(params))

    @get(
        "/months/{year:int}/{month:int}",
        dependencies={
            "historical_context": Provide(provide_historical_context, sync_to_thread=False),
        },
        opt={"pat_permissions": ("workspace.finance.read",), "error_statuses": (404,)},
        description=(
            "Return the finance month identified by year and month, with its "
            "balances and categories.\n\nPersonal API token permissions: "
            "workspace.finance.read."
        ),
        summary="Historical month",
    )
    async def historical_month(
        self,
        use_case: FromDishka[FinanceUseCase],
        historical_context: NamedDependency[FinanceHistoricalMonthParams],
    ) -> FinanceMonthResponse:
        return FinanceMonthResponse.from_domain(await use_case.historical_month(historical_context))

    @get(
        "/months/{year:int}/{month:int}/transactions",
        dependencies={
            "historical_context": Provide(provide_historical_context, sync_to_thread=False),
            "params": Provide(provide_historical_transactions_params, sync_to_thread=False),
        },
        opt={"pat_permissions": ("workspace.finance.read",), "error_statuses": (404,)},
        description=(
            "Return transactions for a historical month. The required "
            "include_deleted query parameter selects whether soft-deleted "
            "entries are included. This list is not paginated.\n\nPersonal API "
            "token permissions: workspace.finance.read."
        ),
        summary="Historical transactions",
    )
    async def historical_transactions(
        self,
        use_case: FromDishka[FinanceUseCase],
        params: NamedDependency[ListHistoricalFinanceTransactionsParams],
    ) -> FinanceTransactionsResponse:
        return FinanceTransactionsResponse.from_domain(
            await use_case.historical_transactions(params),
        )

    @get(
        "/months/{year:int}/{month:int}/transactions/{transaction_id:str}/revisions",
        dependencies={
            "historical_context": Provide(provide_historical_context, sync_to_thread=False),
            "params": Provide(provide_historical_revisions_params, sync_to_thread=False),
        },
        opt={"pat_permissions": ("workspace.finance.read",), "error_statuses": (404,)},
        description=(
            "Return revision history for a transaction in the selected "
            "historical month.\n\nPersonal API token permissions: "
            "workspace.finance.read."
        ),
        summary="Historical revisions",
    )
    async def historical_revisions(
        self,
        use_case: FromDishka[FinanceUseCase],
        params: NamedDependency[HistoricalFinanceRevisionsParams],
    ) -> FinanceRevisionsResponse:
        return FinanceRevisionsResponse.from_domain(await use_case.historical_revisions(params))

    @post(
        "/months/{year:int}/{month:int}/transactions",
        dependencies={
            "historical_context": Provide(provide_historical_context, sync_to_thread=False),
            "params": Provide(provide_historical_create_transaction_params, sync_to_thread=False),
        },
        opt={"pat_permissions": ("workspace.finance.create",), "error_statuses": (400, 404, 503)},
        description=(
            "Record a transaction in the selected historical month using the "
            "supplied category, currency, and occurrence timestamp.\n\nPersonal "
            "API token permissions: workspace.finance.create."
        ),
        summary="Historical create transaction",
    )
    async def historical_create_transaction(
        self,
        use_case: FromDishka[FinanceUseCase],
        params: NamedDependency[CreateFinanceTransactionParams],
    ) -> FinanceTransactionResponse:
        return FinanceTransactionResponse.from_domain(await use_case.create_transaction(params))

    @put(
        "/months/{year:int}/{month:int}/transactions/{transaction_id:str}",
        status_code=status_codes.HTTP_200_OK,
        dependencies={
            "historical_context": Provide(provide_historical_context, sync_to_thread=False),
            "params": Provide(provide_historical_update_transaction_params, sync_to_thread=False),
        },
        opt={
            "pat_permissions": ("workspace.finance.update",),
            "error_statuses": (400, 404, 409, 503),
        },
        description=(
            "Replace a transaction in the selected historical month. Send its "
            "latest version; a stale version returns 409. A revision is "
            "retained.\n\nPersonal API token permissions: workspace.finance.update."
        ),
        summary="Historical update transaction",
    )
    async def historical_update_transaction(
        self,
        use_case: FromDishka[FinanceUseCase],
        params: NamedDependency[UpdateFinanceTransactionParams],
    ) -> FinanceTransactionResponse:
        return FinanceTransactionResponse.from_domain(await use_case.update_transaction(params))

    @delete(
        "/months/{year:int}/{month:int}/transactions/{transaction_id:str}",
        status_code=status_codes.HTTP_200_OK,
        dependencies={
            "historical_context": Provide(provide_historical_context, sync_to_thread=False),
            "params": Provide(provide_historical_delete_transaction_params, sync_to_thread=False),
        },
        opt={
            "pat_permissions": ("workspace.finance.delete",),
            "error_statuses": (400, 404, 409),
        },
        description=(
            "Soft-delete a transaction in the selected historical month. Supply "
            "the latest version query parameter; a stale version returns "
            "409.\n\nPersonal API token permissions: workspace.finance.delete."
        ),
        summary="Historical delete transaction",
    )
    async def historical_delete_transaction(
        self,
        use_case: FromDishka[FinanceUseCase],
        params: NamedDependency[SetFinanceTransactionDeletedParams],
    ) -> FinanceTransactionResponse:
        return FinanceTransactionResponse.from_domain(
            await use_case.set_transaction_deleted(params),
        )

    @post(
        "/months/{year:int}/{month:int}/transactions/{transaction_id:str}/restore",
        status_code=status_codes.HTTP_200_OK,
        dependencies={
            "historical_context": Provide(provide_historical_context, sync_to_thread=False),
            "params": Provide(provide_historical_restore_transaction_params, sync_to_thread=False),
        },
        opt={
            "pat_permissions": ("workspace.finance.update",),
            "error_statuses": (400, 404, 409),
        },
        description=(
            "Restore a soft-deleted transaction in the selected historical month "
            "using its latest version.\n\nPersonal API token permissions: "
            "workspace.finance.update."
        ),
        summary="Historical restore transaction",
    )
    async def historical_restore_transaction(
        self,
        use_case: FromDishka[FinanceUseCase],
        params: NamedDependency[SetFinanceTransactionDeletedParams],
    ) -> FinanceTransactionResponse:
        return FinanceTransactionResponse.from_domain(
            await use_case.set_transaction_deleted(params),
        )

    @get(
        "/statistics",
        dependencies={
            "params": Provide(provide_statistics_params, sync_to_thread=False),
        },
        opt={"pat_permissions": ("workspace.finance.read",), "error_statuses": (404, 503)},
        description=(
            "Return income, expense, category breakdowns, and comparison totals "
            "for the selected reporting period and currency. Month reports "
            "require year and month together. Account time-zone boundaries "
            "determine reporting windows.\n\nPersonal API token permissions: "
            "workspace.finance.read."
        ),
        summary="Statistics",
    )
    async def statistics(
        self,
        use_case: FromDishka[FinanceUseCase],
        params: NamedDependency[FinanceStatisticsParams],
    ) -> FinanceStatisticsResultResponse:
        return FinanceStatisticsResultResponse.from_domain(await use_case.statistics(params))


api_router = DishkaRouter("", route_handlers=[FinanceApiController])
