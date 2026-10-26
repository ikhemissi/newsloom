import asyncio
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import psycopg
import pytest
from azure.identity.aio import ManagedIdentityCredential
from newsloom_core.model_transport import ModelFailure, Vector
from newsloom_core.phase1_contracts import EXPECTED, ROLE, AcceptanceFailure, TestConfig
from newsloom_enrichment.job import run as enrich
from newsloom_enrichment.models import Enrichment
from newsloom_enrichment.repository import Repository as EnrichmentRepository
from newsloom_ingestion.models import DEFAULT_LIMITS, Decision, Entry
from newsloom_ingestion.parsing import parse
from newsloom_platform import phase1_database
from newsloom_platform.config import RuntimeConfig
from phase1_acceptance import run
from phase1_acceptance.fixtures import FixtureClient, sources
from phase1_acceptance.queries import verify
from test_enrichment_database import METADATA, enriched, vector
from test_phase1_contracts import phase_config as phase_config
from test_phase1_database import isolated as isolated
from test_platform_database import platform_database as platform_database


class Scanner:
    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    async def scan(self, entry: Entry, deadline: float) -> Decision:
        hostile = entry.guid is not None and entry.guid.endswith("hostile")
        return Decision(
            "rejected" if hostile else "accepted", "screened", 0.9 if hostile else 0.1, 0.5
        )


class Embeddings:
    async def embed(self, entry: Entry, result: Enrichment, deadline: float) -> Vector:
        return vector()


class QueryEmbedding:
    async def embed(self, query: str, deadline: float) -> Vector:
        return vector()


async def test_authored_document_transport_has_no_network_fallback() -> None:
    client = FixtureClient(DEFAULT_LIMITS)
    cases: list[Entry] = []
    for source in sources():
        document = await client.fetch(str(source.url), {}, 0)
        parsed = parse(source, document.body, document.url, datetime.now(UTC), DEFAULT_LIMITS)
        assert parsed.found == 2 and not parsed.malformed
        cases.extend(candidate.entry() for candidate in parsed.candidates)
    assert {entry.guid for entry in cases} == {
        "rss-benign",
        "rss-hostile",
        "atom-benign",
        "atom-hostile",
    }
    assert all(entry.title and entry.text and entry.author for entry in cases)
    with pytest.raises(AcceptanceFailure, match="unexpected_acceptance_network"):
        await client.fetch("https://example.com/arbitrary", {}, 0)


@pytest.mark.integration
async def test_real_parser_queue_replay_enrichment_and_search_share_actual_local_sql(
    isolated: tuple[RuntimeConfig, TestConfig],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, config = isolated
    async with ManagedIdentityCredential() as credential:
        await phase1_database.prepare(isolated[0], credential, config)
        monkeypatch.setattr(run, "DecisionScanner", Scanner)
        recorder = run.Recorder()
        await run.ingest_and_replay(config, credential, recorder)
        assert [item.name for item in recorder.stages] == ["ingestion", "replay"]

        class Llm:
            async def generate(self, entry: Entry, deadline: float) -> Enrichment:
                return enriched()

        async with await phase1_database.connect(config, credential) as current:
            result = await enrich(
                EnrichmentRepository(current),
                Llm(),
                Embeddings(),
                METADATA,
                config.run_id,
                limit=2,
            )
            assert result["enriched_run"] == 2 and result["failed_run"] == 0
            await verify(current, config, QueryEmbedding(), 0)
        await phase1_database.cleanup(config, credential)


@pytest.mark.parametrize("mode", ["failure", "cancel", "cleanup"])
@pytest.mark.integration
async def test_failed_or_cancelled_main_run_verifies_cleanup_without_faking_success(
    isolated: tuple[RuntimeConfig, TestConfig],
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, config = isolated
    if mode == "failure":
        config = config.model_copy(update={"scenario": "failure-after-ingestion"})
    async with ManagedIdentityCredential() as credential:
        await phase1_database.prepare(isolated[0], credential, config)
        monkeypatch.setattr(run, "DecisionScanner", Scanner)

        async def local_denial(config: TestConfig, credential: object) -> None:
            with pytest.raises(psycopg.OperationalError):
                async with await psycopg.AsyncConnection.connect(
                    os.environ["NEWSLOOM_TEST_POSTGRES_DSN"],
                    dbname="newsloom",
                    user=ROLE,
                ):
                    raise AssertionError("sandbox_connected_to_production")

        monkeypatch.setattr(run, "production_denial", local_denial)
        admitted = asyncio.Event()

        async def blocked(*args: object) -> None:
            admitted.set()
            await asyncio.Future[None]()

        monkeypatch.setattr(run, "recovery", blocked)
        if mode == "cleanup":

            async def failed(*args: object, **kwargs: object) -> None:
                raise psycopg.OperationalError("NEWSLOOM_CREDENTIAL_CANARY")

            monkeypatch.setattr(phase1_database, "cleanup", failed)
        task = asyncio.create_task(run.execute(config, credential))
        if mode != "failure":
            await asyncio.wait_for(admitted.wait(), 5)
            task.cancel()
        report = await asyncio.wait_for(task, 5)
        assert report.outcome == "failure"
        assert report.category == (
            "intentional_failure_after_ingestion" if mode == "failure" else "acceptance_cancelled"
        )
        assert ("cleanup" in {stage.name for stage in report.stages}) == (mode != "cleanup")
        assert "CANARY" not in capsys.readouterr().out


async def test_worker_pipe_is_bounded_and_termination_targets_only_owned_process(
    capsys: pytest.CaptureFixture[str],
) -> None:
    identifier = uuid4().hex
    code = (
        "import json,time;"
        f"print(json.dumps({{'event':'phase1_claim','id':'{identifier}','attempt':1}}),flush=True);"
        "time.sleep(60)"
    )
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        code,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        observed, attempt = await run.first_claim(process)
        assert observed.hex == identifier and attempt == 1
    finally:
        await run.stop(process)
    assert process.returncode is not None and process.returncode != 0
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        "print('NEWSLOOM_CONTENT_CANARY'*10000)",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        with pytest.raises(AcceptanceFailure, match="output_limit"):
            await run.completed_claim(process)
    finally:
        await run.stop(process)
    assert "CANARY" not in capsys.readouterr().out


def test_report_gate_does_not_accept_boolean_or_missing_claim_evidence() -> None:
    for attempt in (True, False, 0, 3, "1"):
        with pytest.raises(AcceptanceFailure):
            run.worker_claim({"event": "phase1_claim", "id": uuid4().hex, "attempt": attempt})
    invalid_counts: tuple[dict[str, int], ...] = ({"manifest": True}, {}, {"manifest": 0})
    for counts in invalid_counts:
        with pytest.raises(ValueError):
            run.Recorder().stage("prepared", counts)
    assert set(EXPECTED) == {
        "prepared",
        "isolation",
        "ingestion",
        "replay",
        "concurrency",
        "recovery",
        "queries",
        "cleanup",
    }


@pytest.mark.integration
async def test_real_processing_refuses_wrong_or_unavailable_scanner_outcomes(
    isolated: tuple[RuntimeConfig, TestConfig],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, config = isolated

    class Incorrect(Scanner):
        async def scan(self, entry: Entry, deadline: float) -> Decision:
            return Decision("accepted", "screened", 0.1, 0.5)

    async with ManagedIdentityCredential() as credential:
        await phase1_database.prepare(isolated[0], credential, config)
        monkeypatch.setattr(run, "DecisionScanner", Incorrect)
        with pytest.raises(AcceptanceFailure, match="fixture_disposition_mismatch"):
            await run.ingest_and_replay(config, credential, run.Recorder())
        async with await phase1_database.connect(config, credential) as current:
            assert await (await current.execute("SELECT count(*) FROM news")).fetchone() == (0,)
        await phase1_database.cleanup(config, credential)


def test_model_operational_errors_keep_a_safe_failure_category() -> None:
    assert run.safe_category(ModelFailure("generation_http_429")) == "generation_http_429"
    assert (
        run.safe_category(psycopg.OperationalError("NEWSLOOM_CREDENTIAL_CANARY"))
        == "operational_error"
    )


async def test_controller_recovery_with_fake_snapshots_uses_real_owned_process_loss(
    phase_config: TestConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original, other = uuid4(), uuid4()
    process_values = [(original, 1, True), (other, 1, False), (original, 2, False)]
    children: list[asyncio.subprocess.Process] = []

    async def spawn(config: TestConfig, *, pause: bool) -> asyncio.subprocess.Process:
        identifier, attempt, expected_pause = process_values[len(children)]
        assert pause == expected_pause
        claim = json.dumps({"event": "phase1_claim", "id": identifier.hex, "attempt": attempt})
        finished = json.dumps({"event": "phase1_worker", "completed": 1})
        code = (
            "import time;print("
            + repr(claim)
            + ",flush=True);"
            + ("time.sleep(60)" if pause else "print(" + repr(finished) + ",flush=True)")
        )
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            code,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        children.append(process)
        return process

    cursor = MagicMock()
    cursor.fetchone = AsyncMock(
        side_effect=[
            ("processing", 1, datetime.now(UTC) + timedelta(seconds=300), True),
            ("processing", 1, False),
            ("processing", 1, True),
            (2, 0, 0, 0),
        ]
    )
    connection = MagicMock(spec=psycopg.AsyncConnection)
    connection.__aenter__ = AsyncMock(return_value=connection)
    connection.__aexit__ = AsyncMock(return_value=False)
    connection.execute = AsyncMock(return_value=cursor)
    monkeypatch.setattr(phase1_database, "connect", AsyncMock(return_value=connection))
    monkeypatch.setattr(run, "spawn", spawn)
    original_sleep = asyncio.sleep

    async def no_delay(seconds: float) -> None:
        await original_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", no_delay)
    recorder = run.Recorder()
    async with ManagedIdentityCredential() as credential:
        await run.recovery(phase_config, credential, recorder)
    assert [stage.name for stage in recorder.stages] == ["concurrency", "recovery"]
    assert children[0].returncode is not None and children[0].returncode < 0
    assert all(child.returncode is not None for child in children)
