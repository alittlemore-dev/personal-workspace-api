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
    include_in_schema = False
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
    )
    async def statistics(
        self,
        use_case: FromDishka[FinanceUseCase],
        params: NamedDependency[FinanceStatisticsParams],
    ) -> FinanceStatisticsResultResponse:
        return FinanceStatisticsResultResponse.from_domain(await use_case.statistics(params))


api_router = DishkaRouter("", route_handlers=[FinanceApiController])
