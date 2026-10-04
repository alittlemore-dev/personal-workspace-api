from datetime import date
from typing import cast
from unittest.mock import Mock

import pytest
from backend_sdk import AuthenticationResult, CredentialTypeEnum, Principal, RoleEnum
from backend_sdk.auth.testing import FakeAuthenticationClient, bearer_headers
from dishka import AsyncContainer
from httpx import codes

from core.calendar.enums import CalendarWindow
from core.calendar.schemas import Calendar, CalendarSummary
from core.finance.use_cases import FinanceUseCase
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
