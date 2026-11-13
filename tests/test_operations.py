"""Operations service: export, operating window and governance tag repair."""

import hashlib
import json
import os
import sys
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import httpx
import psycopg
import pytest
from newsloom_operations import azure, backup

SERVER = "/subscriptions/s/resourceGroups/g/providers/Microsoft.DBforPostgreSQL/flexibleServers/p"
GROUP = "/subscriptions/s/resourceGroups/g"


async def token() -> str:
    return "token"


def manager(handler: httpx.MockTransport) -> tuple[azure.Manager, httpx.AsyncClient]:
    client = httpx.AsyncClient(transport=handler)
    return azure.Manager(client, token, poll=0), client


async def test_start_sends_one_action_and_waits_for_ready() -> None:
    states = iter(["Stopped", "Starting", "Starting", "Ready"])
    calls: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.path}")
        assert request.headers["Authorization"] == "Bearer token"
        if request.method == "POST":
            return httpx.Response(202)
        return httpx.Response(200, json={"properties": {"state": next(states)}})

    arm, client = manager(httpx.MockTransport(handle))
    async with client:
        assert await arm.power(SERVER, "Ready") is True
    assert calls.count(f"POST {SERVER}/start") == 1


async def test_power_is_a_no_op_in_the_target_state() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        return httpx.Response(200, json={"properties": {"state": "Stopped"}})

    arm, client = manager(httpx.MockTransport(handle))
    async with client:
        assert await arm.power(SERVER, "Stopped") is False


async def test_power_waits_out_a_transition_before_acting() -> None:
    states = iter(["Starting", "Ready", "Stopping", "Stopped"])
    posts: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            posts.append(request.url.path)
            return httpx.Response(202)
        return httpx.Response(200, json={"properties": {"state": next(states)}})

    arm, client = manager(httpx.MockTransport(handle))
    async with client:
        assert await arm.power(SERVER, "Stopped") is True
    assert posts == [f"{SERVER}/stop"]


async def test_power_reports_arm_errors_and_timeouts() -> None:
    arm, client = manager(httpx.MockTransport(lambda request: httpx.Response(403)))
    async with client:
        with pytest.raises(azure.Failure, match="arm_get_403"):
            await arm.power(SERVER, "Ready")
    stuck = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"properties": {"state": "Updating"}})
    )
    arm, client = manager(stuck)
    async with client:
        with pytest.raises(azure.Failure, match="database_start_timeout"):
            await arm.power(SERVER, "Ready", within=0.01)


async def test_restore_tags_merges_only_where_missing_and_counts_failures() -> None:
    required = {"CostCenter": "research", "Owner": "lab"}
    tagged = {**required, "project": "newsloom"}
    pages = {
        "1": {
            "value": [
                {"id": f"{GROUP}/providers/x/a", "tags": tagged},
                {"id": f"{GROUP}/providers/x/b", "tags": {"project": "newsloom"}},
            ],
            "nextLink": f"https://management.azure.com{GROUP}/resources?page=2",
        },
        "2": {"value": [{"id": f"{GROUP}/providers/x/c"}]},
    }
    patches: dict[str, object] = {}

    def handle(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "PATCH":
            patches[path] = json.loads(request.content)
            return httpx.Response(403 if "/x/c/" in path else 200)
        if path == GROUP:
            return httpx.Response(200, json={"tags": {"CostCenter": "research"}})
        return httpx.Response(200, json=pages[request.url.params.get("page", "1")])

    arm, client = manager(httpx.MockTransport(handle))
    async with client:
        counts = await arm.restore_tags(GROUP, required)
    suffix = "/providers/Microsoft.Resources/tags/default"
    assert set(patches) == {
        f"{GROUP}{suffix}",
        f"{GROUP}/providers/x/b{suffix}",
        f"{GROUP}/providers/x/c{suffix}",
    }
    assert all(
        body == {"operation": "Merge", "properties": {"tags": required}}
        for body in patches.values()
    )
    assert counts == {"resources": 3, "tagged": 2, "failed": 1}


class Store:
    def __init__(self) -> None:
        self.blobs: dict[str, bytes] = {}

    async def upload(self, name: str, data: AsyncIterator[bytes] | bytes) -> None:
        assert name not in self.blobs
        if isinstance(data, bytes):
            self.blobs[name] = data
            return
        self.blobs[name] = b"".join([chunk async for chunk in data])


def fake_dump(tmp_path: Path, code: int) -> list[str]:
    script = tmp_path / "pg_dump.py"
    script.write_text(
        "import sys\n"
        "assert sys.argv[-1].startswith('--snapshot=')\n"
        "sys.stdout.buffer.write(b'PGDMP' * 1000)\n"
        f"sys.exit({code})\n"
    )
    return [sys.executable, str(script)]


@pytest.fixture
async def connection() -> AsyncIterator[psycopg.AsyncConnection[tuple[object, ...]]]:
    dsn = os.environ.get("NEWSLOOM_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("Explicit local PostgreSQL 18 instance required.")
    async with await psycopg.AsyncConnection.connect(dsn, autocommit=True) as setup:
        await setup.execute("DROP TABLE IF EXISTS public.operations_probe")
        await setup.execute(
            "CREATE TABLE public.operations_probe AS SELECT generate_series(1, 3) id"
        )
        async with await psycopg.AsyncConnection.connect(dsn) as connection:
            yield connection
        await setup.execute("DROP TABLE public.operations_probe")


async def test_export_writes_dump_then_manifest_with_counts_and_checksum(
    connection: psycopg.AsyncConnection[tuple[object, ...]], tmp_path: Path
) -> None:
    store = Store()
    now = datetime(2026, 11, 10, 23, 0, 1, tzinfo=UTC)
    manifest = await backup.export(connection, fake_dump(tmp_path, 0), {}, store, now)
    name = "postgres/2026/11/10/newsloom-20261110T230001Z"
    assert list(store.blobs) == [f"{name}.dump", f"{name}.json"]
    dump = store.blobs[f"{name}.dump"]
    assert manifest["bytes"] == len(dump) == 5000
    assert manifest["sha256"] == hashlib.sha256(dump).hexdigest()
    assert json.loads(store.blobs[f"{name}.json"]) == manifest
    tables = manifest["tables"]
    assert isinstance(tables, dict) and tables["public.operations_probe"] == 3


async def test_failed_dump_never_writes_a_manifest(
    connection: psycopg.AsyncConnection[tuple[object, ...]], tmp_path: Path
) -> None:
    store = Store()
    with pytest.raises(backup.Failure, match="backup_dump_failed"):
        await backup.export(connection, fake_dump(tmp_path, 1), {}, store, datetime.now(UTC))
    assert not any(name.endswith(".json") for name in store.blobs)
    assert store.blobs == {}


async def test_state_storage_access_is_reenabled_only_when_disabled() -> None:
    account = (
        "/subscriptions/s/resourceGroups/g-tfstate/providers/Microsoft.Storage/storageAccounts/st"
    )
    state = {"publicNetworkAccess": "Disabled"}
    patches: list[object] = []

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.path == account
        if request.method == "PATCH":
            patches.append(json.loads(request.content))
            state["publicNetworkAccess"] = "Enabled"
            return httpx.Response(200, json={})
        return httpx.Response(200, json={"properties": dict(state)})

    arm, client = manager(httpx.MockTransport(handle))
    async with client:
        assert await arm.restore_public_access(account) is True
        assert await arm.restore_public_access(account) is False
    assert patches == [{"properties": {"publicNetworkAccess": "Enabled"}}]
