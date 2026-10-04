import json
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest
from sentry_sdk import Client
from sentry_sdk.utils import event_from_exception

from infra.config.initializers import init_sentry
from infra.config.settings import settings


def test_sentry_prepared_event_excludes_request_credentials_and_frame_locals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings.sentry, "use", True)
    with patch("infra.config.initializers.sentry_sdk.init") as initialize:
        init_sentry()
    options = {
        **initialize.call_args.kwargs,
        "dsn": None,
        "integrations": [],
        "default_integrations": False,
        "auto_enabling_integrations": False,
    }
    credential = uuid4().hex
    password = uuid4().hex
    scope = {"headers": [(b"authorization", credential.encode())]}
    client = Client(**options)
    try:
        fail_request(scope=scope, password=password)
    except RuntimeError as error:
        event, hint = event_from_exception(error, client_options=client.options)
    event["request"] = {
        "url": "https://workspace.example/api/resumes",
        "headers": {"Authorization": credential},
        "cookies": {"session": credential},
        "data": {"password": password},
        "query_string": "token=" + credential,
    }
    prepared = client._prepare_event(event, hint, None)  # noqa: SLF001
    serialized = json.dumps(prepared, default=str)
    assert credential not in serialized
    assert password not in serialized
    assert "RuntimeError" in serialized
    assert prepared is not None
    assert prepared["request"] == {"url": "https://workspace.example/api/resumes"}
    transaction = options["before_send_transaction"](
        {
            "request": {
                "url": "https://workspace.example/api/resumes",
                "headers": {"Authorization": credential},
            },
        },
        {},
    )
    assert credential not in json.dumps(transaction)
    client.close()


def fail_request(*, scope: dict[str, Any], password: str) -> None:
    assert scope
    assert password
    message = "Request failed"
    raise RuntimeError(message)
