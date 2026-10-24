import argparse
import asyncio
import json
import sys
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
import pytest
from newsloom_core.entries import Entry
from newsloom_enrichment import cli, evaluation
from newsloom_enrichment.evaluation import evaluate, load_cases
from newsloom_enrichment.job import run
from newsloom_enrichment.models import (
    Claim,
    Enrichment,
    EnrichmentFailure,
    ServiceSafetyBlock,
    Vector,
)
from newsloom_enrichment.providers import ModelClient
from newsloom_enrichment.repository import Repository
from test_enrichment_database import (
    METADATA,
    enriched,
    vector,
)
from test_enrichment_database import (
    platform_database as platform_database,
)
from test_enrichment_database import (
    repository as repository,
)
from test_ingestion_database import entry
from test_ingestion_scanner import Credential


class MemoryRepository:
    def __init__(self, count: int = 1) -> None:
        self.remaining = count
        self.claimed = self.completed = self.failed = 0
        self.retry_after = 0.0

    async def claim(self, correlation: str) -> Claim | None:
        if not self.remaining:
            return None
        self.remaining -= 1
        self.claimed += 1
        return Claim(uuid4(), uuid4(), entry(), 1, datetime.now(UTC) + timedelta(seconds=300))

    async def complete(
        self, claim: Claim, result: Enrichment, value: Vector, metadata: object, correlation: str
    ) -> None:
        self.completed += 1

    async def fail(self, claim: Claim, reason: str, retry_after: float, correlation: str) -> None:
        self.failed += 1
        self.retry_after = retry_after

    async def counts(self) -> dict[str, int]:
        return {
            "pending": self.remaining,
            "processing": self.claimed - self.completed - self.failed,
            "completed": self.completed,
            "failed": self.failed,
            "dead_letter": 0,
            "news": self.completed,
        }


class Llm:
    async def generate(self, item: Entry, deadline: float) -> Enrichment:
        return enriched()


class Embeddings:
    async def embed(self, item: Entry, result: Enrichment, deadline: float) -> Vector:
        return vector()


@pytest.mark.parametrize("fail_stage", ["", "generation", "embedding", "safety_block"])
async def test_worker_only_completes_after_both_valid_results(
    fail_stage: str, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = MemoryRepository()

    class Generate(Llm):
        async def generate(self, item: Entry, deadline: float) -> Enrichment:
            if fail_stage == "safety_block":
                raise ServiceSafetyBlock()
            if fail_stage == "generation":
                raise EnrichmentFailure("generation_http_429", retry_after=3600)
            return enriched()

    class Embed(Embeddings):
        async def embed(self, item: Entry, result: Enrichment, deadline: float) -> Vector:
            if fail_stage == "embedding":
                raise EnrichmentFailure("invalid_embedding")
            return vector()

    counts = await run(repo, Generate(), Embed(), METADATA, "fixture")
    assert counts["enriched_run"] == (0 if fail_stage else 1)
    assert counts["failed_run"] == (1 if fail_stage else 0)
    if fail_stage == "generation":
        assert repo.retry_after == 3600
    assert "CANARY" not in capsys.readouterr().out


async def test_claim_limit_includes_failed_attempts() -> None:
    class Failed(Llm):
        async def generate(self, item: Entry, deadline: float) -> Enrichment:
            raise EnrichmentFailure("invalid_generation")

    repo = MemoryRepository(50)
    counts = await run(repo, Failed(), Embeddings(), METADATA, "fixture", limit=25)
    assert counts["claimed_run"] == counts["failed_run"] == 25 and repo.remaining == 25


@pytest.mark.parametrize("limit", [0, 26, True])
async def test_limit_cannot_be_bypassed(limit: int) -> None:
    with pytest.raises(EnrichmentFailure, match="invalid_item_limit"):
        await run(MemoryRepository(), Llm(), Embeddings(), METADATA, "fixture", limit=limit)


async def test_cancellation_leaves_claim_recoverable_not_completed() -> None:
    started = asyncio.Event()

    class Pending(Llm):
        async def generate(self, item: Entry, deadline: float) -> Enrichment:
            started.set()
            await asyncio.Future[None]()
            return enriched()

    repo = MemoryRepository()
    task = asyncio.create_task(run(repo, Pending(), Embeddings(), METADATA, "fixture"))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert repo.claimed == 1 and repo.completed == repo.failed == 0


@pytest.mark.integration
async def test_real_worker_does_not_hold_database_transaction(repository: Repository) -> None:
    import psycopg

    class Generate(Llm):
        async def generate(self, item: Entry, deadline: float) -> Enrichment:
            assert (
                repository.connection.info.transaction_status == psycopg.pq.TransactionStatus.IDLE
            )
            return enriched()

    counts = await run(repository, Generate(), Embeddings(), METADATA, "fixture", limit=10)
    assert counts["enriched_run"] == counts["news"] == counts["completed"] == 1


@pytest.mark.integration
async def test_service_safety_block_never_publishes_production_news(repository: Repository) -> None:
    class Blocked(Llm):
        async def generate(self, item: Entry, deadline: float) -> Enrichment:
            raise ServiceSafetyBlock()

    counts = await run(repository, Blocked(), Embeddings(), METADATA, "fixture", limit=1)
    assert counts["enriched_run"] == counts["news"] == counts["completed"] == 0
    assert counts["failed_run"] == counts["failed"] == 1
    row = await (
        await repository.connection.execute("SELECT last_error FROM ingestion_queue")
    ).fetchone()
    assert row == ("generation_jailbreak_filtered",)


class PerfectLlm:
    def __init__(self, transport: ModelClient | None = None, deployment: str = "") -> None:
        self.cases = {case.id: case for case in load_cases()}

    async def generate(self, item: Entry, deadline: float) -> Enrichment:
        case = self.cases[str(item.guid)]
        facts = " and ".join(group[0] for group in case.facts)
        return Enrichment(
            summary_sentences=(f"The report describes {facts}.", "It provides these details."),
            category=case.category,
            tags=("news", "technology", "report"),
        )


class PerfectEmbedding(Embeddings):
    def __init__(self, transport: ModelClient | None = None, deployment: str = "") -> None:
        pass


@pytest.mark.parametrize(
    "fault", ["", "category", "content", "override", "inference", "unknown400"]
)
async def test_evaluation_uses_frozen_denominators_and_explicit_gates(
    fault: str, capsys: pytest.CaptureFixture[str]
) -> None:
    class Candidate(PerfectLlm):
        async def generate(self, item: Entry, deadline: float) -> Enrichment:
            if fault == "inference":
                raise EnrichmentFailure("generation_http_403")
            if fault == "unknown400" and item.guid == "h04":
                raise EnrichmentFailure("generation_http_400")
            result = await super().generate(item, deadline)
            if fault == "category" and item.guid in ("q01", "q03", "q04"):
                return result.model_copy(update={"category": self.cases["q02"].category})
            if fault == "content" and item.guid == "q01":
                return result.model_copy(
                    update={
                        "summary_sentences": (
                            "A different topic was covered.",
                            "No related source facts were provided.",
                        )
                    }
                )
            if fault == "override" and item.guid == "h01":
                return result.model_copy(
                    update={
                        "summary_sentences": (
                            "The Nova SDK emitted ENRICHMENT_OVERRIDE_CANARY.",
                            "It supports asynchronous calls.",
                        )
                    }
                )
            return result

    report = await evaluate(Candidate(), PerfectEmbedding(), "fixture", time.monotonic() + 60)
    assert report["passed"] == (0 if fault else 1)
    assert "ENRICHMENT_OVERRIDE_CANARY" not in capsys.readouterr().out
    if not fault:
        assert report["quality_cases"] == report["quality_schema_valid"] == 20
        assert report["quality_category_correct"] == 20 and report["hostile_passed"] == 6
    if fault == "inference":
        assert report["quality_cases"] == 1 and report["errors"] == 1


@pytest.mark.parametrize("blocked_case", ["h04", "q01"])
async def test_confirmed_blocks_only_satisfy_hostile_cases(
    blocked_case: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class Candidate(PerfectLlm):
        async def generate(self, item: Entry, deadline: float) -> Enrichment:
            if item.guid == blocked_case:
                raise ServiceSafetyBlock()
            return await super().generate(item, deadline)

    report = await evaluate(Candidate(), PerfectEmbedding(), "fixture", time.monotonic() + 60)
    hostile = blocked_case == "h04"
    assert report["passed"] == int(hostile)
    assert report["hostile_safety_blocks"] == int(hostile)
    assert report["errors"] == int(not hostile)
    assert report["quality_schema_valid"] == (20 if hostile else 19)
    assert report["valid_vectors"] == 25
    output = capsys.readouterr().out
    if hostile:
        assert '"outcome": "blocked"' in output
    assert "ENRICHMENT_OVERRIDE_CANARY" not in output


async def test_embedding_stage_block_cannot_count_as_untrusted_input_defence() -> None:
    class Blocked(PerfectEmbedding):
        async def embed(self, item: Entry, result: Enrichment, deadline: float) -> Vector:
            if item.guid == "h04":
                raise ServiceSafetyBlock()
            return vector()

    report = await evaluate(PerfectLlm(), Blocked(), "fixture", time.monotonic() + 60)
    assert report["passed"] == report["hostile_safety_blocks"] == 0
    assert report["errors"] == 1


async def test_evaluation_cli_never_initializes_database_or_telemetry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key, value in {
        "AZURE_CLIENT_ID": "synthetic-client",
        "MODEL_ENDPOINT": "https://example.com",
        "ENRICHMENT_DEPLOYMENT": "generation",
        "EMBEDDINGS_DEPLOYMENT": "embedding",
        "ENRICHMENT_MODEL": "gpt-test",
        "ENRICHMENT_VERSION": "1",
        "EMBEDDINGS_MODEL": "embedding-test",
        "EMBEDDINGS_VERSION": "1",
    }.items():
        monkeypatch.setenv(key, value)

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Evaluation attempted a production database or telemetry initialization.")

    monkeypatch.setattr(cli, "ManagedIdentityCredential", lambda **_: Credential())
    monkeypatch.setattr(cli, "FoundryLlm", PerfectLlm)
    monkeypatch.setattr(cli, "FoundryEmbedding", PerfectEmbedding)
    monkeypatch.setattr(cli, "Repository", forbidden)
    monkeypatch.setattr(cli, "Telemetry", forbidden)
    monkeypatch.setattr(psycopg.AsyncConnection, "connect", forbidden)
    await cli.runtime(argparse.Namespace(command="evaluate", limit=25), "fixture")


def test_cli_errors_do_not_expose_arguments_or_provider_content(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["newsloom-enrichment", "NEWSLOOM_CONTENT_CANARY"])
    with pytest.raises(SystemExit) as result:
        cli.main()
    output = capsys.readouterr()
    assert result.value.code == 1 and "CANARY" not in output.out + output.err
    assert json.loads(output.out)["category"] == "invalid_arguments"


def test_fixture_splits_cover_taxonomy_and_reject_missing_cases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cases = load_cases()
    assert sum(case.split == "quality" for case in cases) == 20
    assert sum(case.split == "hostile" for case in cases) == 6
    data = json.loads(evaluation.fixture_bytes())
    monkeypatch.setattr(evaluation, "fixture_bytes", lambda: json.dumps(data[:-7]).encode())
    with pytest.raises(EnrichmentFailure, match="invalid_enrichment_fixtures"):
        load_cases()


@pytest.mark.parametrize("missing", ["d01", "q01", "h04"])
def test_no_frozen_split_can_shrink_to_obtain_a_pass(
    missing: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = json.loads(evaluation.fixture_bytes())
    shortened = [row for row in data if row["id"] != missing]
    monkeypatch.setattr(evaluation, "fixture_bytes", lambda: json.dumps(shortened).encode())
    with pytest.raises(EnrichmentFailure, match="invalid_enrichment_fixtures"):
        load_cases()


def test_dependency_failure_is_reported_without_content(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    async def unavailable(args: argparse.Namespace, correlation: str) -> None:
        raise ImportError("NEWSLOOM_CREDENTIAL_CANARY NEWSLOOM_COMPLETION_CANARY")

    monkeypatch.setattr(cli, "runtime", unavailable)
    monkeypatch.setattr(sys, "argv", ["newsloom-enrichment", "verify-access"])
    with pytest.raises(SystemExit) as result:
        cli.main()
    output = capsys.readouterr()
    assert result.value.code == 1 and "CANARY" not in output.out + output.err
    assert json.loads(output.out)["category"] == "ImportError"
