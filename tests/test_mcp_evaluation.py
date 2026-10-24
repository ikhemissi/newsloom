import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

import psycopg
import pytest
from azure.identity.aio import ManagedIdentityCredential
from newsloom_core.model_transport import ModelFailure, Vector
from newsloom_core.retrieval_fixtures import (
    RetrievalFixtures,
    load_fixtures,
)
from newsloom_mcp.evaluation import eligible, evaluate
from newsloom_mcp.models import SearchInput
from newsloom_mcp.repository import NewsRepository, Repository
from newsloom_platform import database
from newsloom_platform.config import PlatformFailure, RuntimeConfig
from newsloom_platform.mcp_evaluation import cleanup, evaluation_schema, prepare
from psycopg import sql
from pydantic import ValidationError
from test_platform_database import platform_database as platform_database


def test_frozen_groups_cannot_shrink_or_use_missing_relevance() -> None:
    fixtures = load_fixtures()
    assert len(fixtures.corpus) == 22 and len(fixtures.queries) == 20
    assert (
        sum(
            sum(
                eligible(item, SearchInput.model_validate(case.filters)) for item in fixtures.corpus
            )
            > 5
            for case in fixtures.queries
            if case.group == "filtered"
        )
        >= 6
    )
    value = fixtures.model_dump(mode="json")
    for changed in (
        {**value, "queries": value["queries"][:-1]},
        {**value, "queries": [value["queries"][0]] * 20},
        {
            **value,
            "queries": [{**value["queries"][0], "relevant": ["missing"]}, *value["queries"][1:]],
        },
    ):
        with pytest.raises(ValidationError):
            RetrievalFixtures.model_validate(changed)
    for identifier in ("public", "mcp_eval_*", "../../../public", "x" * 32):
        with pytest.raises(PlatformFailure):
            evaluation_schema(identifier)


class DeterministicEmbedding:
    async def embed(self, query: str, deadline: float) -> Vector:
        fixtures = load_fixtures()
        case = next((case for case in fixtures.queries if case.query == query), None)
        identifier = (
            case.relevant[0]
            if case
            else next(item.id for item in fixtures.corpus if item.title in query)
        )
        index = (int(identifier[1:]) - 1) // 2
        return Vector(values=tuple(1.0 if component == index else 0.0 for component in range(1536)))


@pytest.mark.integration
async def test_isolated_real_sql_evaluation_preserves_prod_and_cleans_grant(
    platform_database: RuntimeConfig,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_id = uuid4().hex
    async with ManagedIdentityCredential() as credential:
        await database.migrate(platform_database, credential)
        assert await prepare(platform_database, credential, run_id) == 22
        with pytest.raises(PlatformFailure, match="already_exists"):
            await prepare(platform_database, credential, run_id)

        @asynccontextmanager
        async def repositories() -> AsyncIterator[NewsRepository]:
            async with await database.connect(
                platform_database, credential, "newsloom", "postgres"
            ) as connection:
                await connection.execute("SET SESSION AUTHORIZATION newsloom_mcp")
                async with connection.transaction():
                    await connection.execute(
                        "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
                    )
                    yield Repository(connection, "text-embedding-3-large", "1")

        try:
            report = await evaluate(
                repositories, DeterministicEmbedding(), run_id, time.monotonic() + 120
            )
            assert report["passed"] == 1
            assert report["filtered_recall_at_5"] == report["unfiltered_recall_at_5"] == 1.0
            assert report["filtered_cases"] == report["unfiltered_cases"] == 10
            assert report["filter_violations"] == report["errors"] == 0
            async with repositories() as repository:
                assert isinstance(repository, Repository)
                assert await (
                    await repository.connection.execute("SELECT count(id) FROM public.news")
                ).fetchone() == (0,)
            async with await database.connect(
                platform_database, credential, "newsloom", "postgres"
            ) as reader:
                await reader.execute("SET SESSION AUTHORIZATION newsloom_mcp")
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    async with reader.transaction():
                        await reader.execute(
                            sql.SQL("DELETE FROM {}.news_fixture").format(
                                sql.Identifier(evaluation_schema(run_id))
                            )
                        )
        finally:
            await cleanup(platform_database, credential, run_id)
        async with repositories() as repository:
            assert isinstance(repository, Repository)
            assert (
                await (
                    await repository.connection.execute(
                        "SELECT 1 FROM pg_namespace WHERE nspname=%s", (evaluation_schema(run_id),)
                    )
                ).fetchone()
                is None
            )
        assert "governance" not in capsys.readouterr().out


@pytest.mark.integration
async def test_cleanup_uses_manifest_ownership_and_failure_path(
    platform_database: RuntimeConfig,
) -> None:
    run_id = uuid4().hex
    async with ManagedIdentityCredential() as credential:
        await database.migrate(platform_database, credential)
        await prepare(platform_database, credential, run_id)
        with pytest.raises(PlatformFailure, match="missing"):
            await cleanup(platform_database, credential, uuid4().hex)
        try:
            raise RuntimeError("synthetic evaluation interruption")
        except RuntimeError:
            await cleanup(platform_database, credential, run_id)
        with pytest.raises(PlatformFailure, match="missing"):
            await cleanup(platform_database, credential, run_id)


@pytest.mark.integration
async def test_query_inference_failure_cannot_shrink_the_measured_denominator(
    platform_database: RuntimeConfig,
) -> None:
    run_id = uuid4().hex

    class FailedQueryEmbedding(DeterministicEmbedding):
        async def embed(self, query: str, deadline: float) -> Vector:
            if query == load_fixtures().queries[0].query:
                raise ModelFailure("embedding_http_429")
            return await super().embed(query, deadline)

    async with ManagedIdentityCredential() as credential:
        await database.migrate(platform_database, credential)
        await prepare(platform_database, credential, run_id)

        @asynccontextmanager
        async def repositories() -> AsyncIterator[NewsRepository]:
            async with await database.connect(
                platform_database, credential, "newsloom", "postgres"
            ) as connection:
                await connection.execute("SET SESSION AUTHORIZATION newsloom_mcp")
                async with connection.transaction():
                    await connection.execute(
                        "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
                    )
                    yield Repository(connection, "text-embedding-3-large", "1")

        try:
            report = await evaluate(
                repositories, FailedQueryEmbedding(), run_id, time.monotonic() + 60
            )
            assert report["passed"] == 0 and report["errors"] == 1
            assert report["filtered_cases"] == report["unfiltered_cases"] == 10
            assert report["unfiltered_recall_at_5"] == 0.9
        finally:
            await cleanup(platform_database, credential, run_id)
