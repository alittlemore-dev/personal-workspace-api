from datetime import date
from typing import cast
from unittest.mock import AsyncMock, Mock
from zoneinfo import ZoneInfo

import pytest
from backend_sdk import AuthenticationResult, CredentialTypeEnum, Principal, RoleEnum
from backend_sdk.auth.testing import FakeAuthenticationClient, bearer_headers
from dishka import AsyncContainer
from httpx import codes

from core.calendar.enums import CalendarWindow
from core.calendar.schemas import Calendar, CalendarSummary
from core.finance.assets.analytics_use_cases import AssetAnalyticsStorage, AssetAnalyticsUseCase
from core.finance.assets.reports import AssetReportFacts
from core.finance.assets.services import AssetMovementService
from core.finance.assets.storages import AssetStorage
from core.finance.assets.valuation import AssetRates
from core.finance.exceptions import FinanceNotFoundError
from core.finance.use_cases import FinanceUseCase
from core.telegram.enums import TelegramRuntimeStatus
from core.telegram.use_cases import TelegramUseCase
from infra.config.settings import settings
from infra.valkey.telegram_runtime import TelegramRuntimeStatusStore
from tests.helpers.app import IocContainerHelper
from tests.helpers.factories.core import CoreFactoryHelper
from tests.unit.test_api.test_sdk_authentication import build_sdk_auth_app


def pat_client(*permissions: str, role: RoleEnum = RoleEnum.USER) -> FakeAuthenticationClient:
    client = FakeAuthenticationClient()
    client.set_result(
        AuthenticationResult(
            principal=Principal(username="pat-owner", role=role),
            valid_for_seconds=3600,
            credential_type=CredentialTypeEnum.PAT,
            credential_id="test-pat",
            permissions=frozenset(permissions),
            cache_ttl_seconds=0,
        ),
    )
    return client


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/resumes"),
        ("POST", "/api/resumes"),
        ("GET", "/api/files"),
        ("GET", "/api/vault/recent"),
        ("POST", "/api/tools/cache/clear"),
    ],
)
def test_pat_cannot_cross_domains_without_granted_permissions(
    container: AsyncContainer,
    method: str,
    path: str,
) -> None:
    with build_sdk_auth_app(
        container=container,
        auth_client=pat_client("workspace.calendar.read", role=RoleEnum.OWNER),
    ) as client:
        response = client.request(method, path, headers=bearer_headers(token="alm_pat_test"))  # noqa: S106
    assert response.status_code == codes.FORBIDDEN


async def test_calendar_pat_preserves_owner_filter_and_private_response(
    container: AsyncContainer,
) -> None:
    use_case = await IocContainerHelper(container=container).get_calendar_use_case()
    use_case.get_calendar.return_value = Calendar(
        reference_date=date(2026, 10, 4),
        window=CalendarWindow.CURRENT_AND_NEXT_MONTHS,
        summary=CalendarSummary(memorable_date_count=0, birthday_count=0),
        entries=[],
    )
    with build_sdk_auth_app(
        container=container,
        auth_client=pat_client("workspace.calendar.read"),
    ) as client:
        response = client.get(
            "/api/calendar",
            params={"referenceDate": "2026-10-04", "window": "currentAndNextMonths"},
            headers=bearer_headers(token="alm_pat_test"),  # noqa: S106
        )
    assert response.status_code == codes.OK
    assert response.headers["cache-control"] == "no-store"
    assert use_case.get_calendar.call_args.kwargs["params"].author_username == "pat-owner"


def test_matching_pat_scope_does_not_bypass_admin_role(container: AsyncContainer) -> None:
    with build_sdk_auth_app(
        container=container,
        auth_client=pat_client("workspace.tools.read"),
    ) as client:
        response = client.get("/api/tools/cache", headers=bearer_headers(token="alm_pat_test"))  # noqa: S106
    assert response.status_code == codes.FORBIDDEN


@pytest.mark.parametrize(
    ("method", "path", "granted", "allowed"),
    [
        ("POST", "/api/finance/months/2026/9/transactions/transaction/restore", "create", False),
        ("POST", "/api/finance/months/2026/9/transactions/transaction/restore", "update", True),
        ("DELETE", "/api/finance/current-month/categories/category", "update", False),
        ("DELETE", "/api/finance/current-month/categories/category", "delete", True),
    ],
)
async def test_pat_finance_existing_object_actions_require_correct_permission(
    container: AsyncContainer,
    method: str,
    path: str,
    granted: str,
    allowed: bool,
) -> None:
    use_case = cast("Mock", await container.get(FinanceUseCase))
    factory = CoreFactoryHelper()
    use_case.set_transaction_deleted.return_value = factory.finance_transaction()
    use_case.set_category_archived.return_value = factory.finance_month()
    with build_sdk_auth_app(
        container=container,
        auth_client=pat_client(f"workspace.finance.{granted}"),
    ) as client:
        response = client.request(
            method,
            path,
            json={"version": 1} if method == "POST" else None,
            headers=bearer_headers(token="alm_pat_test"),  # noqa: S106
        )
    assert response.status_code == (codes.OK if allowed else codes.FORBIDDEN)
    operation = (
        use_case.set_transaction_deleted if method == "POST" else use_case.set_category_archived
    )
    if allowed:
        operation.assert_awaited_once()
        assert operation.await_args.args[0].owner_username == "pat-owner"
    else:
        operation.assert_not_awaited()


@pytest.mark.parametrize(("granted", "allowed"), [("create", False), ("update", True)])
async def test_pat_resume_photo_replacement_requires_update_permission(
    container: AsyncContainer,
    granted: str,
    allowed: bool,
) -> None:
    use_case = await IocContainerHelper(container=container).get_resumes_use_case()
    resume = CoreFactoryHelper().resume(resume_id=3)
    use_case.upload_photo.return_value = resume
    with build_sdk_auth_app(
        container=container,
        auth_client=pat_client(f"workspace.resumes.{granted}"),
    ) as client:
        response = client.post(
            f"/api/resumes/{resume.id}/photo",
            files={"file": ("photo.jpg", b"jpeg-bytes", "image/jpeg")},
            headers=bearer_headers(token="alm_pat_test"),  # noqa: S106
        )
    assert response.status_code == (codes.OK if allowed else codes.FORBIDDEN)
    if allowed:
        use_case.upload_photo.assert_awaited_once()
        assert use_case.upload_photo.await_args.kwargs["params"].author_username == "pat-owner"
    else:
        use_case.upload_photo.assert_not_awaited()


async def test_assets_read_only_report_from_empty_tracker_and_revocation(
    container: AsyncContainer,
) -> None:
    storage, journal = AsyncMock(spec=AssetAnalyticsStorage), AsyncMock(spec=AssetStorage)
    journal.list_positions.return_value = []
    journal.list_movements.return_value = []
    storage.facts.return_value = AssetReportFacts(zone=ZoneInfo("UTC"), incomes=[], goals=[])
    storage.rates.return_value = AssetRates(ordered=[])
    service = cast("Mock", await container.get(AssetAnalyticsUseCase))
    service.report.side_effect = AssetAnalyticsUseCase(storage=storage, journal=journal).report
    auth = pat_client("workspace.assets.read")
    with build_sdk_auth_app(container=container, auth_client=auth) as client:
        headers = bearer_headers(token="alm_pat_test")  # noqa: S106
        path = "/api/finance/assets/report?start=2026-03-01&end=2026-03-31&currency=RUB"
        read = client.get(path, headers=headers)
        assert read.status_code == codes.OK
        assert read.headers["cache-control"] == "no-store"
        assert read.json()["coverageStart"] is None
        assert read.json()["coverageEnd"] is None
        assert read.json()["closing"]["positions"] == []
        assert read.json()["netSavings"] == "0"
        journal.list_positions.assert_awaited_once_with(owner_username="pat-owner")
        assert (
            client.post(
                "/api/finance/assets/locations",
                headers=headers,
                json={"name": "Reserve"},
            ).status_code
            == codes.FORBIDDEN
        )
        auth.set_invalid_credentials()
        assert client.get(path, headers=headers).status_code == codes.UNAUTHORIZED


@pytest.mark.parametrize("session", [True, False])
async def test_budget_contribution_requires_both_pat_permissions_before_writing(
    container: AsyncContainer,
    session: bool,
) -> None:
    auth = (
        FakeAuthenticationClient(username="owner")
        if session
        else pat_client("workspace.assets.create")
    )
    use_case = cast("Mock", await container.get(AssetMovementService))
    use_case.apply.side_effect = FinanceNotFoundError
    with build_sdk_auth_app(container=container, auth_client=auth) as client:
        response = client.post(
            "/api/finance/assets/movements",
            headers=bearer_headers(token="test"),  # noqa: S106
            json={
                "kind": "contribution",
                "onDate": "2026-03-12",
                "amount": "10.00",
                "positionId": "another-owner",
                "requestId": "cfc74a46-0807-493e-9f53-0cd5da684688",
            },
        )
    if session:
        assert response.status_code == codes.NOT_FOUND
        assert use_case.apply.await_args.args[0].owner_username == "owner"
    else:
        assert response.status_code == codes.FORBIDDEN
        use_case.apply.assert_not_awaited()


@pytest.mark.parametrize(
    ("permissions", "asset_flag", "expected"),
    [
        (("workspace.telegram.update",), None, codes.OK),
        (("workspace.telegram.update",), False, codes.FORBIDDEN),
        (("workspace.assets.read",), True, codes.FORBIDDEN),
        (("workspace.telegram.update", "workspace.assets.read"), True, codes.OK),
    ],
)
async def test_asset_subscription_permissions(
    container: AsyncContainer,
    permissions: tuple[str, ...],
    asset_flag: bool | None,
    expected: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings.telegram, "available", True)
    telegram = cast("Mock", await container.get(TelegramUseCase))
    telegram.set_connection_settings.return_value = CoreFactoryHelper().telegram_connection(
        owner_username="pat-owner",
    )
    payload = {
        "notifyBirthday": False,
        "notifyMemorableDate": False,
        "notifyFinanceTransaction": False,
        "notifyFinanceLimit": False,
        "language": "ru",
    }
    if asset_flag is not None:
        payload["notifyAssetMovement"] = asset_flag
    with build_sdk_auth_app(container=container, auth_client=pat_client(*permissions)) as client:
        client.app.state.telegram_runtime_state.status = TelegramRuntimeStatus.READY
        store = Mock(spec=TelegramRuntimeStatusStore)
        store.is_ready = AsyncMock(return_value=True)
        client.app.state.telegram_runtime_status = store
        response = client.put(
            "/api/telegram/connections/example/settings",
            headers=bearer_headers(token="alm_pat_test"),  # noqa: S106
            json=payload,
        )
    assert response.status_code == expected
    if expected == codes.OK:
        params = telegram.set_connection_settings.await_args.kwargs["params"]
        assert params.settings.notify_asset_movement is asset_flag
    else:
        telegram.set_connection_settings.assert_not_awaited()


@pytest.mark.parametrize("scope", ["workspace.assets.read", "workspace.finance.read"])
async def test_asset_opening_preview_requires_both_read_scopes(
    container: AsyncContainer,
    scope: str,
) -> None:
    with build_sdk_auth_app(container=container, auth_client=pat_client(scope)) as client:
        response = client.post(
            "/api/finance/assets/opening-preview",
            headers=bearer_headers(token="alm_pat_test"),  # noqa: S106
            json={"positionId": "reserve", "amount": "25.00", "onDate": "2026-03-12"},
        )
    assert response.status_code == codes.FORBIDDEN
