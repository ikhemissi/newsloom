"""Explicit operator checks; never registered as tools or run at service startup."""

import asyncio
import re
import time
from uuid import UUID

import httpx
import psycopg
from azure.core.credentials_async import AsyncTokenCredential
from azure.identity.aio import ManagedIdentityCredential
from newsloom_core.retrieval_fixtures import load_fixtures
from psycopg import sql

from newsloom_mcp.evaluation import eligible
from newsloom_mcp.models import DetailInput, McpFailure, RecentInput, SearchInput
from newsloom_mcp.repository import Repository
from newsloom_mcp.runtime import Config, resources


def require(condition: bool, category: str) -> None:
    if not condition:
        raise McpFailure(category)


async def verify_news(
    repository: Repository, run_id: str | None
) -> tuple[SearchInput, dict[str, int]]:
    connection = repository.connection
    require(
        await (await connection.execute("SELECT current_user")).fetchone() == ("newsloom_mcp",),
        "verification_identity_mismatch",
    )
    if run_id is not None:
        row = await (
            await connection.execute(
                "SELECT 1 FROM pg_namespace WHERE nspname=%s",
                ("mcp_eval_" + UUID(run_id).hex,),
            )
        ).fetchone()
        require(row is None, "evaluation_schema_still_present")
    recent = await repository.recent(RecentInput(limit=5))
    require(bool(recent.items), "verification_news_required")
    expected = await (
        await connection.execute("SELECT id FROM public.news ORDER BY published_at DESC,id LIMIT 5")
    ).fetchall()
    require(
        [item.id for item in recent.items] == [row[0] for row in expected],
        "verification_recent_mismatch",
    )
    first = recent.items[0]
    detail = await repository.detail(DetailInput(id=first.id))
    if not detail.found or detail.item is None:
        raise McpFailure("verification_detail_missing")
    require(
        detail.item.model_dump(include=set(type(first).model_fields)) == first.model_dump(),
        "verification_detail_mismatch",
    )
    stored = await (
        await connection.execute(
            "SELECT id,title,summary,source,category,tags,published_at,canonical_url,"
            "author,date_origin,publisher_categories FROM public.news WHERE id=%s",
            (first.id,),
        )
    ).fetchone()
    if stored is None or not isinstance(stored[5], list) or not isinstance(stored[10], list):
        raise McpFailure("verification_stored_detail_invalid")
    item = detail.item
    require(
        (
            item.id,
            item.title,
            item.summary,
            item.source,
            item.category,
            item.tags,
            item.published_at,
            item.url,
            item.author,
            item.date_origin,
            item.publisher_categories,
        )
        == (*stored[:5], tuple(stored[5]), *stored[6:10], tuple(stored[10])),
        "verification_stored_detail_mismatch",
    )
    discovery = await repository.sources()
    associations = await (
        await connection.execute("SELECT DISTINCT source,category FROM public.news")
    ).fetchall()
    require(
        {
            (source.id, category.value)
            for source in discovery.sources
            for category in source.categories
        }
        == set(associations)
        and {category.id.value for category in discovery.categories}
        == {row[1] for row in associations},
        "verification_discovery_mismatch",
    )
    args = SearchInput(
        source=first.source,
        category=first.category,
        tags=first.tags[:2],
        from_=first.published_at,
        limit=5,
    )
    metadata = await repository.search(args, None)
    require(
        first.id in {item.id for item in metadata.items}
        and all(eligible(item, args) and item.similarity is None for item in metadata.items),
        "verification_metadata_mismatch",
    )
    count = await (await connection.execute("SELECT count(id) FROM public.news")).fetchone()
    if count is None or not isinstance(count[0], int) or count[0] < 1:
        raise McpFailure("verification_count_invalid")
    return args, {
        "news": count[0],
        "recent_ids": len(expected),
        "cleanup_checks": int(run_id is not None),
    }


async def require_denied(
    connection: psycopg.AsyncConnection[tuple[object, ...]],
    statement: sql.SQL | sql.Composed,
) -> None:
    try:
        async with connection.transaction(force_rollback=True):
            await connection.execute(statement)
    except psycopg.errors.InsufficientPrivilege:
        return
    raise McpFailure("verification_database_denial_not_proven")


async def verify_database_denials(repository: Repository) -> int:
    connection = repository.connection
    # Test ACLs rather than having READ ONLY reject the probes before permission checks.
    await connection.execute("SET TRANSACTION READ WRITE")
    statements = (
        "SELECT 1 FROM public.ingestion_queue LIMIT 0",
        "SELECT 1 FROM public.quarantine LIMIT 0",
        "SELECT * FROM public.news LIMIT 0",
        "UPDATE public.news SET title=title WHERE false",
        "DELETE FROM public.news WHERE false",
        "CREATE TABLE public.newsloom_mcp_permission_probe (id integer)",
        "CREATE SCHEMA newsloom_mcp_permission_probe",
        "SET ROLE newsloom_ingestion",
        "SET ROLE newsloom_enrichment",
        "SET ROLE azure_pg_admin",
    )
    for statement in statements:
        await require_denied(connection, sql.SQL(statement))
    return len(statements)


async def verify_http(
    config: Config,
    credential: AsyncTokenCredential,
    client: httpx.AsyncClient,
    generation: str,
    screening: str,
) -> dict[str, int]:
    request = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    headers = {"Accept": "application/json, text/event-stream"}
    response = await client.post(config.resource_url, headers=headers, json=request)
    require(response.status_code == 401, "verification_anonymous_denial_not_proven")
    model_token = await credential.get_token("https://cognitiveservices.azure.com/.default")
    model_headers = {"Authorization": "Bearer " + model_token.token}
    response = await client.post(
        config.resource_url,
        headers={**headers, **model_headers},
        json=request,
    )
    require(response.status_code == 401, "verification_resource_denial_not_proven")
    for path, model in (
        ("/openai/v1/chat/completions", generation),
        ("/providers/microsoft/v1/systemone", screening),
    ):
        response = await client.post(
            config.model_endpoint.rstrip("/") + path,
            headers=model_headers,
            json={"model": model},
        )
        require(response.status_code in (401, 403), "verification_model_denial_not_proven")
    api_token = await credential.get_token(f"api://{config.audience}/.default")
    for method in ("initialize", "tools/list", "tools/call"):
        response = await client.post(
            config.resource_url,
            headers={**headers, "Authorization": "Bearer " + api_token.token},
            json={**request, "method": method},
        )
        require(response.status_code == 403, "verification_app_only_denial_not_proven")
    return {
        "anonymous_denials": 1,
        "wrong_resource_denials": 1,
        "model_denials": 2,
        "app_only_denials": 3,
    }


async def verify_access(
    config: Config,
    generation: str,
    screening: str,
    run_id: str | None,
) -> dict[str, int]:
    if any(
        not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", name)
        for name in (generation, screening)
    ):
        raise McpFailure("invalid_verification_deployment")
    if run_id is not None:
        run_id = UUID(run_id).hex
    async with asyncio.timeout(180):
        async with resources(config, instrument=False) as (services, _):
            async with services.repositories() as repository:
                if not isinstance(repository, Repository):
                    raise McpFailure("verification_repository_required")
                args, counts = await verify_news(repository, run_id)
            query = load_fixtures().development[0].get("query")
            if not isinstance(query, str):
                raise McpFailure("invalid_development_query")
            args = SearchInput.model_validate({**args.model_dump(by_alias=True), "query": query})
            vector = await services.embeddings.embed(query, time.monotonic() + 90)
            async with services.repositories() as repository:
                ranked = await repository.search(args, vector.values)
                require(
                    bool(ranked.items)
                    and all(
                        eligible(item, args) and item.similarity is not None
                        for item in ranked.items
                    ),
                    "verification_semantic_mismatch",
                )
            async with services.repositories() as repository:
                if not isinstance(repository, Repository):
                    raise McpFailure("verification_repository_required")
                counts["database_denials"] = await verify_database_denials(repository)
        async with (
            ManagedIdentityCredential(client_id=str(config.client_id)) as credential,
            httpx.AsyncClient(timeout=20, follow_redirects=False) as client,
        ):
            counts.update(await verify_http(config, credential, client, generation, screening))
    return {**counts, "tool_checks": 5, "embedding_dimensions": len(vector.values)}
