from datetime import UTC, datetime

from backend_sdk import Principal
from backend_sdk.integrations.litestar import AuthContext
from litestar import Request
from litestar.datastructures import State

from core.vault.schemas import GetVaultStatisticsParams


def provide_statistics_params(
    request: Request[Principal, AuthContext, State],
) -> GetVaultStatisticsParams:
    return GetVaultStatisticsParams(
        author_username=request.user.username,
        current_datetime=datetime.now(tz=UTC),
    )
