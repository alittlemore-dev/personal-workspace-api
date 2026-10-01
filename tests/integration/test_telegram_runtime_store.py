import asyncio
import os
import shutil
import subprocess
import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from valkey.asyncio import Valkey
from valkey.exceptions import ConnectionError as ValkeyConnectionError

from infra.valkey.telegram_runtime import TelegramRuntimeStatusStore


@pytest_asyncio.fixture
async def runtime_valkey() -> AsyncGenerator[Valkey]:
    docker = shutil.which("docker")
    assert docker is not None
    container = await asyncio.to_thread(
        subprocess.run,
        [
            docker,
            "run",
            "--detach",
            "--rm",
            "--publish",
            "127.0.0.1::6379",
            os.environ["TELEGRAM_TEST_VALKEY_IMAGE"],
            "valkey-server",
            "--save",
            "",
            "--appendonly",
            "no",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    container_id = container.stdout.strip()
    client: Valkey | None = None
    try:
        published = await asyncio.to_thread(
            subprocess.run,
            [docker, "port", container_id, "6379/tcp"],
            check=True,
            capture_output=True,
            text=True,
        )
        address = published.stdout.strip()
        hostname, port = address.rsplit(":", 1)
        client = Valkey(host=hostname, port=int(port), socket_timeout=1)
        async with asyncio.timeout(10):
            while True:
                try:
                    await client.ping()
                    break
                except ValkeyConnectionError:
                    await asyncio.sleep(0.05)
        yield client
    finally:
        if client is not None:
            await client.aclose(close_connection_pool=True)
        await asyncio.to_thread(
            subprocess.run,
            [docker, "rm", "--force", container_id],
            check=True,
            capture_output=True,
        )


@pytest.mark.asyncio
async def test_real_valkey_route_lease_and_late_failure_compare_and_swap(
    runtime_valkey: Valkey,
    global_random_uuid: uuid.UUID,
) -> None:
    store = TelegramRuntimeStatusStore(
        valkey=runtime_valkey,
        key=f"test-runtime:{global_random_uuid}",
        ttl_seconds=90,
        pool_id="test-pool",
        route_count=2,
    )
    assert not await store.is_ready()
    await store.publish_ready(0)
    assert await store.get_ready_route() == 0
    assert await runtime_valkey.ttl(store.key) > 0

    await store.publish_ready(1)
    assert not await store.mark_failed(0)
    assert await store.get_ready_route() == 1
    assert await store.mark_failed(1)
    assert not await store.is_ready()

    await store.publish_ready(0)
    changed_pool = TelegramRuntimeStatusStore(
        valkey=runtime_valkey,
        key=store.key,
        ttl_seconds=90,
        pool_id="different-pool",
        route_count=2,
    )
    assert not await changed_pool.is_ready()
    assert not await changed_pool.mark_failed(0)
    assert await store.get_ready_route() == 0

    await runtime_valkey.pexpire(store.key, 1)
    await asyncio.sleep(0.05)
    assert not await store.is_ready()
    assert await store.get_ready_route() is None
    for malformed in (b"1", b"null", b'"ready"', b"[]", b"invalid-json"):
        await runtime_valkey.set(store.key, malformed, ex=90)
        assert not await store.is_ready()
        assert not await store.mark_failed(0)
