from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from azure.identity.aio import ManagedIdentityCredential
from newsloom_enrichment.repository import Repository
from newsloom_platform import database
from newsloom_platform import evaluation_reconciliation as r
from newsloom_platform import evaluation_record_probe as probe
from newsloom_platform.config import PlatformFailure, RuntimeConfig, json_object
from psycopg import AsyncConnection, AsyncCursor
from psycopg.abc import Params, QueryNoTemplate
from test_enrichment_database import (
    METADATA,
    enriched,
    seed,
    vector,
)
from test_enrichment_database import (
    repository as repository,
)
from test_platform_database import platform_database as platform_database

pytestmark = pytest.mark.integration


async def legacy(
    connection: AsyncConnection[tuple[object, ...]],
) -> dict[str, object]:
    import hashlib
    import json

    rows = await (
        await connection.execute(
            "SELECT id::text,md5(row_to_json(n)::text) "
            f"FROM (SELECT {probe.METADATA} FROM public.news) AS n ORDER BY id"
        )
    ).fetchall()
    recent = await (
        await connection.execute(
            "SELECT id::text,canonical_url FROM public.news ORDER BY published_at DESC,id LIMIT 1"
        )
    ).fetchone()
    assert recent is not None
    return {
        "news_count": len(rows),
        "news_metadata_fingerprint": hashlib.sha256(
            json.dumps(rows, separators=(",", ":")).encode()
        ).hexdigest(),
        "recent_id_sha256": probe.sha(str(recent[0])),
        "recent_url_sha256": probe.sha(str(recent[1])),
        "verified_utc": datetime.now(UTC).isoformat(),
    }


async def test_real_postgres_reconstructs_both_exact_historical_receipts_and_denies_writes(
    repository: Repository,
    platform_database: RuntimeConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    claim = await repository.claim("initial")
    assert claim is not None
    await repository.complete(claim, enriched(), vector(), METADATA, "initial")
    connection = repository.connection
    before = await legacy(connection)
    await seed(platform_database, count=1, offset=1)
    claim = await repository.claim("added")
    assert claim is not None
    await repository.complete(claim, enriched(), vector(), METADATA, "added")
    failed = await legacy(connection)
    async with (
        ManagedIdentityCredential() as credential,
        await database.connect(platform_database, credential, "newsloom", "postgres") as admin,
    ):
        original = admin.execute
        denied: list[bool] = []

        async def execute(
            query: QueryNoTemplate,
            params: Params | None = None,
            *,
            prepare: bool | None = None,
            binary: bool = False,
        ) -> AsyncCursor[tuple[object, ...]]:
            if isinstance(query, str) and query.startswith("SELECT id::text"):
                with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
                    async with admin.transaction():
                        await original("DELETE FROM public.news")
                denied.append(True)
            return await original(query, params, prepare=prepare, binary=binary)

        monkeypatch.setattr(admin, "execute", execute)
        value = await probe.collect(
            admin, (str(before["verified_utc"]), str(failed["verified_utc"])), "postgres"
        )
        assert denied == [True]
        assert r.reconstructed(value, before, failed) == [1, 1, 0]
        assert r.parse_lines("\n".join(probe.lines(value))) == value
        assert value["news_count"] == 2 and value["writes_performed"] == 0
        assert len(probe.encoded(value)) < 512 * 1024
        assert admin.info.transaction_status == psycopg.pq.TransactionStatus.IDLE
        assert (await (await original("SELECT count(*) FROM public.news")).fetchone()) == (2,)


@pytest.mark.parametrize("difference", ["changed", "deleted", "wrong_cutoff"])
async def test_historical_reconstruction_cannot_infer_preservation_from_growth(
    repository: Repository,
    platform_database: RuntimeConfig,
    difference: str,
) -> None:
    claim = await repository.claim("initial")
    assert claim is not None
    await repository.complete(claim, enriched(), vector(), METADATA, "initial")
    original = await legacy(repository.connection)
    failed = await legacy(repository.connection)
    async with (
        ManagedIdentityCredential() as credential,
        await database.connect(platform_database, credential, "newsloom", "postgres") as admin,
    ):
        if difference == "deleted":
            await admin.execute("DELETE FROM public.news")
            with pytest.raises(ValueError, match="row_limit"):
                await probe.collect(
                    admin, (str(original["verified_utc"]), str(failed["verified_utc"])), "postgres"
                )
            return
        if difference == "changed":
            await admin.execute("UPDATE public.news SET title='Changed fixture'")
        else:
            original["verified_utc"] = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        if difference == "wrong_cutoff":
            with pytest.raises(ValueError, match="subset_empty"):
                await probe.collect(
                    admin, (str(original["verified_utc"]), str(failed["verified_utc"])), "postgres"
                )
            return
        value = await probe.collect(
            admin, (str(original["verified_utc"]), str(failed["verified_utc"])), "postgres"
        )
        with pytest.raises(PlatformFailure, match="historical_fingerprint"):
            r.reconstructed(value, original, failed)


async def test_mcp_can_collect_complete_v1_fingerprints_without_hidden_column_grants(
    repository: Repository,
    platform_database: RuntimeConfig,
) -> None:
    claim = await repository.claim("initial")
    assert claim is not None
    await repository.complete(claim, enriched(), vector(), METADATA, "initial")
    async with (
        ManagedIdentityCredential() as credential,
        await database.connect(platform_database, credential, "newsloom", "postgres") as connection,
    ):
        await connection.execute("SET ROLE newsloom_mcp")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            await connection.execute("SELECT created_at FROM public.news")
        value = await probe.collect(connection, None, "newsloom_mcp")
        assert value["identity_sha256"] == probe.sha("newsloom_mcp")
        assert value["historical_membership"] == [] and value["reconstructions"] == []
        assert len(r.records(value)) == 1
        assert json_object(value)["read_only"] is True


async def test_probe_rejects_unenforced_read_only_before_reading_any_news(
    repository: Repository,
    platform_database: RuntimeConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = AsyncConnection.set_read_only

    async def force_read_write(
        connection: AsyncConnection[tuple[object, ...]],
        value: bool | None,
    ) -> None:
        await original(connection, False)

    monkeypatch.setattr(AsyncConnection, "set_read_only", force_read_write)
    async with (
        ManagedIdentityCredential() as credential,
        await database.connect(platform_database, credential, "newsloom", "postgres") as connection,
    ):
        now = datetime.now(UTC)
        with pytest.raises(ValueError, match="read_only_not_enforced"):
            await probe.collect(
                connection, ((now - timedelta(seconds=1)).isoformat(), now.isoformat()), "postgres"
            )
