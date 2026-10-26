import asyncio
import json
import re
import sys
import time
from datetime import datetime
from uuid import UUID

import httpx
import psycopg
from azure.core.credentials_async import AsyncTokenCredential
from azure.core.exceptions import AzureError
from newsloom_core.model_transport import ModelClient, ModelFailure
from newsloom_core.phase1_contracts import (
    EXPECTED,
    ROLE,
    AcceptanceFailure,
    CaseResult,
    Report,
    Stage,
    TestConfig,
    fixture_revision,
    load_fixtures,
)
from newsloom_ingestion.job import run as ingest
from newsloom_ingestion.models import DEFAULT_LIMITS, IngestionFailure
from newsloom_ingestion.repository import Repository as IngestionRepository
from newsloom_ingestion.scanner import DecisionScanner, calibration_id
from newsloom_mcp.embedding import FoundryQueryEmbedding
from newsloom_mcp.models import McpFailure
from newsloom_platform import phase1_database
from psycopg import sql
from pydantic import ValidationError

from phase1_acceptance.fixtures import FixtureClient, sources
from phase1_acceptance.queries import verify as verify_queries

ERRORS = (
    AcceptanceFailure,
    ModelFailure,
    IngestionFailure,
    McpFailure,
    ValidationError,
    psycopg.Error,
    httpx.HTTPError,
    AzureError,
    TimeoutError,
    OSError,
    ValueError,
)


def safe_category(error: BaseException) -> str:
    if isinstance(error, (AcceptanceFailure, ModelFailure, IngestionFailure, McpFailure)):
        value = str(error)
        if re.fullmatch(r"[a-z0-9_]{1,80}", value):
            return value
    return re.sub(r"(?<!^)(?=[A-Z])", "_", type(error).__name__).lower()[:80]


class Recorder:
    def __init__(self) -> None:
        self.stages: list[Stage] = []
        self.cases: list[CaseResult] = []
        self.last = time.monotonic()

    def stage(self, name: str, counts: dict[str, int]) -> None:
        now = time.monotonic()
        current = Stage.model_validate(
            {
                "name": name,
                "counts": counts,
                "elapsed_seconds": now - self.last,
            }
        )
        if any(stage.name == current.name for stage in self.stages):
            raise AcceptanceFailure("duplicate_acceptance_stage")
        self.stages.append(current)
        self.last = now
        print(
            json.dumps(
                {
                    "event": "phase1_stage",
                    "stage": name,
                    "counts": counts,
                }
            ),
            flush=True,
        )


async def production_denial(config: TestConfig, credential: AsyncTokenCredential) -> None:
    token = await credential.get_token("https://ossrdbms-aad.database.windows.net/.default")
    try:
        current = await psycopg.AsyncConnection.connect(
            host=config.postgres_host,
            dbname="newsloom",
            user=ROLE,
            password=token.token,
            sslmode="verify-full",
            sslrootcert="/etc/ssl/certs/ca-certificates.crt",
            connect_timeout=15,
            autocommit=True,
        )
    except psycopg.OperationalError as error:
        if error.sqlstate == "42501" or re.search(
            r'\bFATAL:\s+permission denied for database "?newsloom"?(?:\s|$)',
            str(error),
        ):
            return
        raise AcceptanceFailure("production_database_denial_not_proven") from None
    await current.close()
    raise AcceptanceFailure("production_database_access_not_denied")


async def isolation(config: TestConfig, credential: AsyncTokenCredential) -> None:
    await production_denial(config, credential)
    async with await phase1_database.connect(config, credential) as current:
        for role in ("azure_pg_admin", "newsloom_ingestion", "newsloom_enrichment", "newsloom_mcp"):
            try:
                async with current.transaction(force_rollback=True):
                    await current.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(role)))
            except psycopg.errors.InsufficientPrivilege:
                continue
            raise AcceptanceFailure("production_role_access_not_denied")


async def ingest_and_replay(
    config: TestConfig,
    credential: AsyncTokenCredential,
    recorder: Recorder,
) -> None:
    expected = calibration_id(
        config.model_endpoint,
        config.screening_deployment,
        config.screening_model,
        config.screening_version,
        config.scanner_threshold,
    )
    if expected != config.scanner_calibration_id:
        raise AcceptanceFailure("acceptance_scanner_calibration_mismatch")
    async with (
        httpx.AsyncClient() as client,
        await phase1_database.connect(config, credential) as current,
    ):
        scanner = DecisionScanner(
            client,
            credential,
            config.model_endpoint,
            config.screening_deployment,
            config.scanner_threshold,
        )
        repository = IngestionRepository(current, config.screening_model, config.screening_version)
        counts = await ingest(
            sources(),
            repository,
            scanner,
            config.run_id,
            force=True,
            client=FixtureClient(DEFAULT_LIMITS),
        )
        rows = await (
            await current.execute(
                "SELECT guid,disposition,reason,score,threshold FROM public.quarantine"
            )
        ).fetchall()
        for row in rows:
            case = CaseResult.model_validate(
                {
                    "id": row[0],
                    "disposition": "accepted" if row[1] == "resolved" else row[1],
                    "reason": row[2],
                    "score": row[3],
                    "threshold": row[4],
                }
            )
            recorder.cases.append(case)
            print(json.dumps({"event": "phase1_case", **case.model_dump()}), flush=True)
        expected_rows = {
            (case.id, "rejected" if case.hostile else "resolved") for case in load_fixtures().cases
        }
        if {(row[0], row[1]) for row in rows} != expected_rows:
            raise AcceptanceFailure("acceptance_fixture_disposition_mismatch")
        recorder.stage(
            "ingestion",
            {
                "found": counts["found"],
                "accepted": counts["accepted_run"],
                "rejected": counts["rejected_run"],
                "deferred": counts["deferred_run"],
            },
        )
        if config.scenario == "failure-after-ingestion":
            raise AcceptanceFailure("intentional_failure_after_ingestion")
        before = await (
            await current.execute(
                "SELECT id,guid FROM ingestion_queue UNION ALL "
                "SELECT id,guid FROM quarantine ORDER BY id"
            )
        ).fetchall()
        replay = await ingest(
            sources(),
            repository,
            scanner,
            config.run_id,
            force=True,
            client=FixtureClient(DEFAULT_LIMITS),
        )
        after = await (
            await current.execute(
                "SELECT id,guid FROM ingestion_queue UNION ALL "
                "SELECT id,guid FROM quarantine ORDER BY id"
            )
        ).fetchall()
        if (
            before != after
            or replay["accepted_run"]
            or replay["rejected_run"]
            or replay["deferred_run"]
        ):
            raise AcceptanceFailure("acceptance_replay_identity_mismatch")
        recorder.stage("replay", {"duplicates": replay["duplicates"], "staged": replay["staged"]})


async def stop(process: asyncio.subprocess.Process) -> None:
    if process.returncode is None:
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), 10)
        except TimeoutError:
            process.kill()
            await asyncio.wait_for(process.wait(), 10)


async def spawn(config: TestConfig, *, pause: bool) -> asyncio.subprocess.Process:
    return await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "phase1_acceptance",
        "worker",
        "--run-id",
        config.run_id,
        *(["--pause-after-claim"] if pause else []),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        limit=65536,
    )


def worker_claim(value: object) -> tuple[UUID, int]:
    if (
        not isinstance(value, dict)
        or value.get("event") != "phase1_claim"
        or not isinstance(value.get("id"), str)
        or type(value.get("attempt")) is not int
        or value["attempt"] not in (1, 2)
    ):
        raise AcceptanceFailure("invalid_acceptance_claim")
    return UUID(value["id"]), value["attempt"]


async def first_claim(process: asyncio.subprocess.Process) -> tuple[UUID, int]:
    if process.stdout is None:
        raise AcceptanceFailure("acceptance_worker_output_missing")
    async with asyncio.timeout(60):
        for _ in range(50):
            line = await process.stdout.readline()
            if not line:
                break
            value: object = json.loads(line)
            if isinstance(value, dict) and value.get("event") == "phase1_claim":
                return worker_claim(value)
    raise AcceptanceFailure("acceptance_worker_claim_missing")


async def completed_claim(process: asyncio.subprocess.Process) -> tuple[UUID, int]:
    async def bounded(stream: asyncio.StreamReader | None, limit: int) -> bytes:
        if stream is None:
            raise AcceptanceFailure("acceptance_worker_output_missing")
        result = bytearray()
        while chunk := await stream.read(min(4096, limit + 1 - len(result))):
            result.extend(chunk)
            if len(result) > limit:
                raise AcceptanceFailure("acceptance_worker_output_limit")
        return bytes(result)

    async with asyncio.timeout(300):
        stdout, stderr, _ = await asyncio.gather(
            bounded(process.stdout, 65536),
            bounded(process.stderr, 8192),
            process.wait(),
        )
    if len(stdout) > 65536 or stderr or process.returncode != 0:
        raise AcceptanceFailure("acceptance_worker_failed")
    claims = []
    finished = 0
    for line in stdout.splitlines():
        value: object = json.loads(line)
        if isinstance(value, dict) and value.get("event") == "phase1_claim":
            claims.append(worker_claim(value))
        if (
            isinstance(value, dict)
            and value.get("event") == "phase1_worker"
            and type(value.get("completed")) is int
            and value.get("completed") == 1
        ):
            finished += 1
    if len(claims) != 1 or finished != 1:
        raise AcceptanceFailure("acceptance_worker_evidence_missing")
    return claims[0]


async def recovery(
    config: TestConfig,
    credential: AsyncTokenCredential,
    recorder: Recorder,
) -> None:
    processes: list[asyncio.subprocess.Process] = []
    try:
        interrupted = await spawn(config, pause=True)
        processes.append(interrupted)
        original, attempt = await first_claim(interrupted)
        if attempt != 1:
            raise AcceptanceFailure("acceptance_initial_claim_mismatch")
        async with await phase1_database.connect(config, credential) as current:
            row = await (
                await current.execute(
                    "SELECT status,attempts,lease_until,lease_until>clock_timestamp() "
                    "FROM ingestion_queue WHERE id=%s",
                    (original,),
                )
            ).fetchone()
            if (
                row is None
                or row[:2] != ("processing", 1)
                or not isinstance(row[2], datetime)
                or row[3] is not True
            ):
                raise AcceptanceFailure("acceptance_committed_claim_missing")
        print(json.dumps({"event": "phase1_checkpoint", "stage": "claim_committed"}), flush=True)
        if config.scenario == "cancel-after-claim":
            await asyncio.Future[None]()
        concurrent = await spawn(config, pause=False)
        processes.append(concurrent)
        other, other_attempt = await completed_claim(concurrent)
        if other == original or other_attempt != 1:
            raise AcceptanceFailure("acceptance_concurrent_claim_mismatch")
        await stop(interrupted)
        if interrupted.returncode is None or interrupted.returncode == 0:
            raise AcceptanceFailure("acceptance_process_loss_not_observed")
        recorder.stage("concurrency", {"distinct_claims": 2, "lost_workers": 1})
        async with asyncio.timeout(330):
            while True:
                async with await phase1_database.connect(config, credential) as current:
                    row = await (
                        await current.execute(
                            "SELECT status,attempts,lease_until<=clock_timestamp() "
                            "FROM ingestion_queue "
                            "WHERE id=%s",
                            (original,),
                        )
                    ).fetchone()
                if row == ("processing", 1, True):
                    break
                if row is None or row[:2] != ("processing", 1):
                    raise AcceptanceFailure("acceptance_lease_changed_before_recovery")
                await asyncio.sleep(2)
        reclaimed = await spawn(config, pause=False)
        processes.append(reclaimed)
        recovered, recovered_attempt = await completed_claim(reclaimed)
        if recovered != original or recovered_attempt != 2:
            raise AcceptanceFailure("acceptance_reclaimed_identity_mismatch")
        async with await phase1_database.connect(config, credential) as current:
            row = await (
                await current.execute(
                    "SELECT (SELECT count(*) FROM news),"
                    "(SELECT count(*) FROM ingestion_queue WHERE status<>'completed'),"
                    "(SELECT count(*) FROM (SELECT canonical_url FROM news GROUP BY canonical_url "
                    "HAVING count(*)>1) d),"
                    "(SELECT count(*) FROM news n JOIN quarantine q "
                    "ON n.canonical_url=q.canonical_url "
                    "WHERE q.disposition='rejected')"
                )
            ).fetchone()
            if row is None or any(type(item) is not int for item in row):
                raise AcceptanceFailure("invalid_acceptance_integrity_counts")
            counts: dict[str, int] = {}
            for name, value in zip(
                ("completed", "unfinished", "duplicates", "published_rejections"),
                row,
                strict=True,
            ):
                if not isinstance(value, int) or isinstance(value, bool):
                    raise AcceptanceFailure("invalid_acceptance_integrity_counts")
                counts[name] = value
        recorder.stage("recovery", {"attempt": recovered_attempt, **counts})
    finally:
        for process in processes:
            await stop(process)


async def execute(config: TestConfig, credential: AsyncTokenCredential) -> Report:
    recorder = Recorder()
    category = ""
    try:
        async with asyncio.timeout(1100):
            async with await phase1_database.connect(config, credential) as current:
                result = await (
                    await current.execute(
                        "UPDATE newsloom_acceptance_admin.manifest SET started=true "
                        "WHERE NOT started RETURNING singleton"
                    )
                ).fetchone()
                if result != (True,):
                    raise AcceptanceFailure("acceptance_run_already_started")
            recorder.stage("prepared", {"manifest": 1})
            await isolation(config, credential)
            recorder.stage("isolation", EXPECTED["isolation"])
            await ingest_and_replay(config, credential, recorder)
            await recovery(config, credential, recorder)
            async with (
                httpx.AsyncClient() as client,
                await phase1_database.connect(config, credential) as current,
            ):
                transport = ModelClient(client, credential, config.model_endpoint)
                await verify_queries(
                    current,
                    config,
                    FoundryQueryEmbedding(transport, config.embedding_deployment),
                    time.monotonic() + 90,
                )
            recorder.stage("queries", EXPECTED["queries"])
    except ERRORS as error:
        category = safe_category(error)
    except asyncio.CancelledError:
        category = "acceptance_cancelled"
    finally:
        try:
            async with asyncio.timeout(60):
                await phase1_database.cleanup(config, credential)
            recorder.stage("cleanup", {"absent": 1})
        except ERRORS as error:
            failure = safe_category(error)
            print(json.dumps({"event": "phase1_cleanup_failure", "category": failure}), flush=True)
            category = category or "acceptance_cleanup_failed"
    return Report(
        run_id=config.run_id,
        scenario=config.scenario,
        outcome="failure" if category else "success",
        category=category,
        fixture_revision=fixture_revision(),
        schema_revision=phase1_database.schema_revision(),
        model_revision=config.model_revision(),
        image_revision=config.image_revision,
        stages=tuple(recorder.stages),
        cases=tuple(recorder.cases),
    )
