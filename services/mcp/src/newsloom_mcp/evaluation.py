"""Real embedding/SQL retrieval over isolated read-only authored corpus projections."""

import json
import re
import time
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from uuid import UUID

import psycopg
from newsloom_core.diagnostics import event
from newsloom_core.model_transport import ModelFailure
from newsloom_core.retrieval_fixtures import (
    CorpusItem,
    corpus_uuid,
    fixture_revision,
    load_fixtures,
)
from psycopg import sql
from pydantic import ValidationError

from newsloom_mcp.embedding import QueryEmbedding
from newsloom_mcp.models import McpFailure, NewsItem, SearchInput
from newsloom_mcp.repository import NewsRepository, Repository


def eligible(item: CorpusItem | NewsItem, filters: SearchInput) -> bool:
    return (
        (filters.source is None or item.source == filters.source)
        and (filters.category is None or item.category == filters.category)
        and all(tag in item.tags for tag in filters.tags)
        and (filters.from_ is None or item.published_at >= filters.from_)
        and (filters.to is None or item.published_at < filters.to)
    )


async def evaluate(
    repositories: Callable[[], AbstractAsyncContextManager[NewsRepository]],
    embedding: QueryEmbedding,
    run_id: str,
    deadline: float,
) -> dict[str, int | float | str]:
    if not re.fullmatch(r"[a-f0-9]{32}", run_id):
        raise McpFailure("invalid_evaluation_run_id")
    schema = "mcp_eval_" + UUID(hex=run_id).hex
    fixtures = load_fixtures()
    parsed = {}
    for case in fixtures.queries:
        args = SearchInput.model_validate({"query": case.query, "limit": 5, **case.filters})
        relevant = {
            item.id for item in fixtures.corpus if item.id in case.relevant and eligible(item, args)
        }
        if relevant != set(case.relevant):
            raise McpFailure("invalid_filtered_relevance")
        parsed[case.id] = args
    async with repositories() as repository:
        if not isinstance(repository, Repository):
            raise McpFailure("invalid_evaluation_repository")
        marker = await (
            await repository.connection.execute(
                sql.SQL("SELECT run_id,revision FROM {}.manifest").format(sql.Identifier(schema))
            )
        ).fetchone()
    if marker != (run_id, fixture_revision()):
        raise McpFailure("evaluation_manifest_mismatch")
    vectors = []
    for item in fixtures.corpus:
        if time.monotonic() >= deadline:
            raise McpFailure("evaluation_deadline")
        text = json.dumps(
            {
                "title": item.title,
                "summary": item.summary,
                "source": item.source,
                "category": item.category.value,
                "tags": item.tags,
            }
        )
        vector = await embedding.embed(text, deadline)
        vectors.append(
            {
                "id": str(corpus_uuid(item.id)),
                "value": "[" + ",".join(map(str, vector.values)) + "]",
            }
        )
    relation = sql.SQL(
        "(SELECT f.*,v.value::vector AS embedding FROM {}.news_fixture f "
        "JOIN jsonb_to_recordset(%s::jsonb) AS v(id uuid,value text) USING(id)) AS corpus"
    ).format(sql.Identifier(schema))
    ids = {corpus_uuid(item.id): item for item in fixtures.corpus}
    values = json.dumps(vectors)
    cases = {"filtered": 0, "unfiltered": 0}
    totals = {"filtered": 0.0, "unfiltered": 0.0}
    violations = errors = 0
    for case in fixtures.queries:
        args = parsed[case.id]
        recall = 0.0
        observed: list[str] = []
        similarities = ""
        category = ""
        try:
            vector = await embedding.embed(case.query, deadline)
            async with repositories() as repository:
                if not isinstance(repository, Repository):
                    raise McpFailure("invalid_evaluation_repository")
                result = await repository.rank(args, vector.values, relation, [values])
            if any(item.id not in ids or item.similarity is None for item in result.items):
                raise McpFailure("invalid_evaluation_result")
            observed = [ids[item.id].id for item in result.items]
            similarities = ",".join(
                f"{item.similarity:.6f}" for item in result.items if item.similarity is not None
            )
            violations += sum(not eligible(item, args) for item in result.items)
            recall = len(set(observed) & set(case.relevant)) / len(case.relevant)
        except (McpFailure, ModelFailure) as error:
            category = str(error)
            errors += 1
        except psycopg.Error, ValidationError:
            category = "evaluation_operation_failed"
            errors += 1
        cases[case.group] += 1
        totals[case.group] += recall
        event(
            "mcp_evaluation_case",
            run_id,
            outcome="failure" if category else "observed",
            category=case.id,
            counts={
                "group": case.group,
                "relevant": ",".join(case.relevant),
                "retrieved": ",".join(observed),
                "similarities": similarities,
                "recall_at_5": recall,
                "error": category,
            },
        )
    means = {group: totals[group] / 10 for group in cases}
    passed = (
        cases == {"filtered": 10, "unfiltered": 10}
        and min(means.values()) >= 0.8
        and violations == errors == 0
    )
    report: dict[str, int | float | str] = {
        "passed": int(passed),
        "filtered_cases": cases["filtered"],
        "unfiltered_cases": cases["unfiltered"],
        "filtered_recall_at_5": means["filtered"],
        "unfiltered_recall_at_5": means["unfiltered"],
        "filter_violations": violations,
        "errors": errors,
        "fixture_revision": fixture_revision(),
    }
    event("mcp_evaluation", run_id, outcome="success" if passed else "failure", counts=report)
    return report
