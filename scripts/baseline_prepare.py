"""Prepare one agent-quality baseline snapshot (profile ``baseline-14x10-v9``).

Replaces the per-attempt operator scripts. Subcommands run in order: ``start``,
``readiness``, ``freeze``, ``approve`` and, after a stopped run, ``record-usage``.
Private state lives under ``.azure/dev/agent-quality-baseline/<snapshot>/`` (0700
directories, 0600 files written once with ``O_EXCL``). Stdout is metadata-only JSON;
failures print ``{"outcome":"failure","category":...}`` and exit 1. No step deploys,
applies or calls a model. Run from the repository root with
``uv run --locked python -m scripts.baseline_prepare <command>``.
"""

import argparse
import asyncio
import base64
import contextlib
import hashlib
import json
import os
import re
import subprocess
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from itertools import count
from pathlib import Path
from typing import Any
from uuid import uuid4

from newsloom_agent.models import AgentFailure
from newsloom_platform.config import PlatformFailure

from scripts.baseline_evaluator_step import FROZEN, LAYERS, PROFILE, SNAPSHOT_VERSION, SUITE
from scripts.baseline_evaluator_step import write_private as _write_private

ROOT = Path(__file__).resolve().parents[1]
STATE = Path(".azure/dev/agent-quality-baseline")
EVALUATOR = Path("tools/agent-evaluation")
HELPER = Path("scripts/baseline_evaluator_step.py")
WINDOW = timedelta(minutes=30)
LIMITS = {"metadata_before": 180, "auth_http": 40, "evidence": 160, "sign_ins": 9}
EVIDENCE_BYTES = 10 * 1024 * 1024
AZD_AGENT = {"AZURE_DEV_USER_AGENT": "microsoft_foundry_skill"}
AZD_VALUES = ["azd", "env", "get-values", "--environment", "dev", "--output", "json"]
OWNING = {
    "application": "infra",
    "agent": "infra/agent",
    "agent-evaluation": "infra/agent-evaluation",
}
PRICES_URL = "https://prices.azure.com/api/retail/prices"
CHAT_SKUS = ("5.4 mini Inp Dz", "5.4 mini cd Inp Dz", "5.4 mini Opt Dz")
NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,62}")
MAX_REUSED_CALIBRATION = 1024 * 1024


class PrepareFailure(Exception):
    """A fixed metadata-only category."""


def utcnow() -> datetime:
    return datetime.now(UTC)


def run(
    arguments: Sequence[str],
    *,
    cwd: Path,
    timeout: float,
    env: dict[str, str] | None = None,
    log: Path | None = None,
) -> subprocess.CompletedProcess[bytes]:
    if log is None:
        return subprocess.run(
            list(arguments), cwd=cwd, env=env, capture_output=True, timeout=timeout, check=False
        )
    descriptor = os.open(log, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        return subprocess.run(
            list(arguments),
            cwd=cwd,
            env=env,
            stdout=stream,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )


def emit(value: object) -> None:
    print(json.dumps(value, sort_keys=True), flush=True)


def write_private(path: Path, data: bytes) -> bytes:
    try:
        return _write_private(path, data)
    except FileExistsError:
        raise PrepareFailure("baseline_record_exists") from None


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_private(path: Path) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as stream:
        return stream.read()


@dataclass(frozen=True)
class Snapshot:
    root: Path
    name: str

    def __post_init__(self) -> None:
        if not NAME.fullmatch(self.name):
            raise PrepareFailure("baseline_snapshot_name_invalid")

    @property
    def base(self) -> Path:
        return self.root / STATE / self.name

    def read(self, relative: str) -> bytes:
        return read_private(self.base / relative)

    def load(self, relative: str) -> Any:
        return json.loads(self.read(relative))

    def save(self, relative: str, value: object, *, indent: int | None = None) -> bytes:
        data = json.dumps(value, sort_keys=True, allow_nan=False, indent=indent).encode()
        return write_private(self.base / relative, data)

    def directory(self, relative: str) -> Path:
        path = self.base / relative
        path.mkdir(mode=0o700, exist_ok=True)
        os.chmod(path, 0o700)
        return path

    def expires(self) -> datetime:
        return datetime.fromisoformat(self.load("authorization-v2.json")["readiness_expires_at"])

    def remaining(self) -> float:
        return (self.expires() - utcnow()).total_seconds()

    def require_window(self) -> float:
        remaining = self.remaining()
        if remaining <= 0:
            raise PrepareFailure("baseline_readiness_authorization_expired")
        return remaining

    def reserve(self, operation: str, amount: int = 1) -> None:
        self.require_window()
        operations = self.load("operations.json")
        counts = operations["counts"]
        if operation == "semantic_evidence":
            raise PrepareFailure("baseline_preparation_inference_forbidden")
        if operation == "evidence_bytes":
            received = operations.get("evidence_response_bytes", 0)
            if amount < 0 or received + amount > EVIDENCE_BYTES:
                raise PrepareFailure("baseline_preparation_byte_limit")
            operations["evidence_response_bytes"] = received + amount
        else:
            maximum = LIMITS.get(operation)
            if maximum is None or amount < 0 or counts.get(operation, 0) + amount > maximum:
                raise PrepareFailure("baseline_readiness_operation_limit")
            counts[operation] = counts.get(operation, 0) + amount
        temporary = self.base / "operations.next"
        write_private(temporary, json.dumps(operations, sort_keys=True).encode())
        temporary.replace(self.base / "operations.json")

    def rotate(self, name: str) -> str | None:
        """Keep a partial earlier attempt as ``failed-<name>-N`` instead of overwriting it."""
        path = self.base / name
        if not path.exists() and not path.is_symlink():
            return None
        stem, suffix = (name[: -len(path.suffix)], path.suffix) if path.suffix else (name, "")
        for index in count(1):
            target = self.base / f"failed-{stem}-{index}{suffix}"
            if not target.exists() and not target.is_symlink():
                path.rename(target)
                return target.name
        raise AssertionError  # pragma: no cover


def snapshot_for(name: str) -> Snapshot:
    return Snapshot(ROOT, name)


# start


def start(
    snapshot: Snapshot, prior_usage: Path, prior_run: Path, instruction: str
) -> dict[str, object]:
    usage_bytes = read_private(prior_usage)
    usage = json.loads(usage_bytes)
    budget_bytes = read_private(prior_run / "budget.json")
    budget = json.loads(budget_bytes)
    exposure = usage["estimated_usd"]
    try:
        observed = Decimal(exposure["total_observed_chat"])
        reserved = Decimal(exposure["total_unmeasured_reserved"])
        combined = Decimal(exposure["conservative_combined_exposure"])
    except InvalidOperation:
        raise PrepareFailure("baseline_start_prior_usage_invalid") from None
    if (
        observed + reserved != combined
        or usage.get("budget_receipt_sha256", digest(budget_bytes)) != digest(budget_bytes)
        or not budget.get("halted")
    ):
        raise PrepareFailure("baseline_start_prior_usage_mismatch")
    approvals: list[str] = []
    try:
        earlier = json.loads(read_private(prior_run.parents[1] / "prior-history.json"))
        approvals.extend(earlier.get("snapshot4_prior_approvals", []))
    except FileNotFoundError, IndexError:
        pass
    if budget["approval_sha256"] not in approvals:
        approvals.append(budget["approval_sha256"])
    parent = snapshot.base.parent
    parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        snapshot.base.mkdir(mode=0o700)
    except FileExistsError:
        raise PrepareFailure("baseline_snapshot_exists") from None
    now = utcnow()
    history = {
        "outcome": "prior_attempts_preserved",
        "estimated_usd": exposure,
        "prior_usage_sha256": digest(usage_bytes),
        "prior_operations_sha256": digest(budget_bytes),
        "prior_counters": budget["counts"],
        "prior_failed_baseline_expiry": budget["original_expires_at"],
        "prior_halt": usage.get("failure_category", usage["outcome"]),
        "snapshot4_prior_approvals": approvals,
        "old_journals_modified": False,
    }
    expires = now + WINDOW
    for name, value in (
        ("prior-history.json", history),
        (
            "authorization-v2.json",
            {
                "user_instruction": instruction,
                "scope": "fresh_snapshot4_readiness_v9",
                "snapshot_version": SNAPSHOT_VERSION,
                "suite_version": SUITE,
                "limit_profile": PROFILE,
                "bound_readiness_started_at": now.isoformat(),
                "readiness_expires_at": expires.isoformat(),
                "prior_history_sha256": digest(json.dumps(history, sort_keys=True).encode()),
                "cumulative_model_ceiling_usd": "100",
                "deployment_intended": False,
                "old_run_resumed": False,
                "model_calls_in_readiness": 0,
            },
        ),
        (
            "operations.json",
            {
                "counts": {"metadata_before": 0, "auth_http": 0, "evidence": 0, "sign_ins": 0},
                "evidence_response_bytes": 0,
                "model_calls": 0,
                "snapshot_version": SNAPSHOT_VERSION,
                "per_run_counter_scope": "new_explicit_approval",
            },
        ),
    ):
        snapshot.save(name, value)
    return {
        "outcome": "snapshot4_readiness_started",
        "started_at": now.isoformat(),
        "expires_at": expires.isoformat(),
        "prior_exposure_usd": exposure["conservative_combined_exposure"],
        "previous_counters_preserved": True,
        "model_calls": 0,
    }


# readiness


def local_json(
    snapshot: Snapshot, arguments: list[str], category: str, *, azd: bool = False
) -> dict[str, Any]:
    environment = dict(os.environ)
    if azd:
        environment.update(AZD_AGENT)
    result = run(
        arguments,
        cwd=snapshot.root,
        env=environment,
        timeout=max(1.0, min(60.0, snapshot.require_window())),
    )
    if result.returncode or len(result.stdout) > 1024 * 1024:
        raise PrepareFailure(category)
    data = json.loads(result.stdout)
    if not isinstance(data, dict):
        raise PrepareFailure(category)
    return data


def observe_metadata(snapshot: Snapshot) -> dict[str, object]:
    from newsloom_platform import evaluation_verification as v
    from newsloom_platform.agent_evaluation import OPERATOR_TOKEN

    authorization = snapshot.load("authorization-v2.json")
    snapshot.require_window()
    snapshot.directory("observations")
    snapshot.reserve("metadata_before", 2)
    env = local_json(snapshot, AZD_VALUES, "baseline_readiness_context_failed", azd=True)
    if any(not isinstance(value, str) for value in env.values()):
        raise PrepareFailure("baseline_readiness_environment_invalid")
    account = local_json(
        snapshot,
        ["az", "account", "show", "--only-show-errors", "--output", "json"],
        "baseline_readiness_context_failed",
    )
    user = account.get("user")
    if (
        env.get("AZURE_ENV_NAME") != "dev"
        or account.get("id") != env.get("AZURE_SUBSCRIPTION_ID")
        or account.get("tenantId") != env.get("AGENT_TENANT_ID")
        or account.get("state") != "Enabled"
        or not isinstance(user, dict)
        or user.get("type") != "user"
    ):
        raise PrepareFailure("baseline_readiness_account_mismatch")
    del account, user
    keep = (
        set(v.CONTEXT)
        | set(v.APPLICATIONS)
        | {
            "MCP_TENANT_ID",
            "MCP_RESOURCE_URL",
            "AGENT_RESOURCE_URL",
            "AGENT_IMAGE",
            "AGENT_IMAGE_REVISION",
            "AGENT_APP_ID",
            "AGENT_APP_NAME",
            "AZURE_CONTAINER_REGISTRY_ENDPOINT",
            "AZURE_CONTAINER_APPS_ENVIRONMENT_ID",
            "AGENT_EVALUATION_PROJECT_ID",
            "AGENT_EVALUATION_PROJECT_ENDPOINT",
        }
    )
    snapshot.save(
        "observations/context.json", {key: value for key, value in env.items() if key in keep}
    )
    snapshot.save(
        "observations/authorization.json",
        {
            "user_authorization": authorization["user_instruction"],
            "bound_readiness_started_at": authorization["bound_readiness_started_at"],
            "readiness_expires_at": authorization["readiness_expires_at"],
            "paid_profile": PROFILE,
            "maximum_model_usd": "100",
            "deployment_intended": False,
            "no_model_calls_in_readiness": True,
        },
    )
    reader = v.Reader(env, execution=False)
    reader.deadline = time.monotonic() + min(600, snapshot.require_window())
    original = reader.cli

    def bounded(arguments: list[str]) -> object:
        reader.guard(arguments)
        operator = arguments == OPERATOR_TOKEN
        snapshot.reserve("auth_http" if operator else "metadata_before")
        return original(arguments)

    reader.cli = bounded  # type: ignore[method-assign]
    token = reader.cli(OPERATOR_TOKEN)
    if not isinstance(token, str):
        raise PrepareFailure("baseline_readiness_operator_missing")
    parts = token.split(".")
    claims = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
    if (
        claims.get("tid") != env.get("AGENT_TENANT_ID")
        or claims.get("oid") != env.get("AGENT_EVALUATION_OPERATOR_PRINCIPAL_ID")
        or claims.get("exp", 0) <= time.time()
    ):
        raise PrepareFailure("baseline_readiness_operator_mismatch")
    del token, claims, parts
    scoped = v.snapshot(reader, env)
    snapshot.save("observations/scoped-before.json", scoped)
    snapshot.save(
        "observations/context-status.json",
        {
            "outcome": "observed",
            "metadata_observed_at": utcnow().isoformat(),
            "read_operations": reader.calls,
            "counts": snapshot.load("operations.json")["counts"],
            "snapshot_sha256": v.digest(scoped),
            "context_sha256": v.digest({key: env[key] for key in v.CONTEXT}),
            "model_calls": 0,
            "mutations": 0,
            "migration_executions": 0,
        },
    )
    return {"outcome": "readiness_metadata_observed", "reads": reader.calls, "model_calls": 0}


def prepare_evidence(snapshot: Snapshot) -> dict[str, object]:
    snapshot.directory("evidence")
    try:
        return asyncio.run(_prepare_evidence(snapshot))
    except (PrepareFailure, AgentFailure, PlatformFailure) as error:
        _evidence_failure(snapshot, [error])
        raise
    except Exception as error:
        leaves = _leaves(error)
        _evidence_failure(snapshot, leaves)
        known = [leaf for leaf in leaves if isinstance(leaf, PrepareFailure | AgentFailure)]
        raise PrepareFailure(str(known[0]) if known else "baseline_preparation_failed") from None


def _leaves(error: BaseException) -> list[BaseException]:
    pending, leaves = [error], []
    while pending:
        item = pending.pop()
        if isinstance(item, BaseExceptionGroup):
            pending.extend(item.exceptions)
        else:
            leaves.append(item)
    return leaves


def _evidence_failure(snapshot: Snapshot, leaves: list[BaseException]) -> None:
    locations = []
    for item in leaves:
        trace = item.__traceback__
        while trace is not None:
            locations.append(
                {"file": Path(trace.tb_frame.f_code.co_filename).name, "line": trace.tb_lineno}
            )
            trace = trace.tb_next
    known = (PrepareFailure, AgentFailure, PlatformFailure)
    diagnostic = {
        "outcome": "failure",
        "category": "baseline_preparation_failed",
        "error_types": sorted({type(item).__name__ for item in leaves}),
        "agent_categories": [str(item) for item in leaves if isinstance(item, known)],
        "locations": locations,
    }
    with contextlib.suppress(PrepareFailure, OSError):
        snapshot.save("evidence/failure.json", diagnostic)


async def _prepare_evidence(snapshot: Snapshot) -> dict[str, object]:
    import httpx
    from newsloom_agent.research_models import NewsResults, SearchResults

    from scripts.agent_quality_capture import (
        CaptureLimits,
        CaptureSettings,
        configure_operator_browser,
        evidence_session,
        fingerprint,
        sign_in_agent,
    )

    remaining = snapshot.require_window()

    def permit(operation: str, amount: int) -> None:
        try:
            snapshot.reserve(operation, amount)
        except PrepareFailure as error:
            raise AgentFailure(str(error)) from None

    permit("metadata_before", 1)
    loaded = run(
        AZD_VALUES, cwd=snapshot.root, env={**os.environ, **AZD_AGENT}, timeout=min(60, remaining)
    )
    if loaded.returncode:
        raise PrepareFailure("baseline_preparation_environment_failed")
    env = json.loads(loaded.stdout)
    settings = CaptureSettings.from_environment(env)
    operations = snapshot.load("operations.json")
    counts = operations["counts"]
    limits = CaptureLimits(
        operations=counts["evidence"],
        auth_requests=counts["auth_http"],
        sign_ins=counts["sign_ins"],
        received=operations["evidence_response_bytes"],
        metadata_reads=counts["metadata_before"],
        limit_profile="baseline-14x10-v9",
        deadline=time.monotonic() + min(600, snapshot.require_window()),
        permit=permit,
    )
    configure_operator_browser()
    emit({"outcome": "awaiting_existing_user_sign_in", "model_calls": 0})
    async with httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=30) as public:
        _token, caller = await sign_in_agent(settings, public, limits)
        del _token
        async with evidence_session(settings, caller, limits, readiness=True) as reader:
            recent = await reader.call("get_recent_news", {"limit": 5})
            if not isinstance(recent, NewsResults) or len(recent.items) < 3:
                raise AgentFailure("baseline_preparation_insufficient_recent_items")
            details = []
            for item in recent.items:
                detail = await reader.item(item.id)
                if detail is None:
                    raise AgentFailure("baseline_preparation_item_disappeared")
                details.append(detail)
            n1 = next(
                (
                    item
                    for item in details
                    if item.tags
                    and all(re.fullmatch(r"[a-z0-9][a-z0-9 +#.-]{0,47}", tag) for tag in item.tags)
                ),
                None,
            )
            if n1 is None:
                raise AgentFailure("baseline_preparation_missing_constrained_tags")
            chosen = [n1, *(item for item in details if item.id != n1.id)][:3]
            begin = n1.published_at.astimezone(UTC)
            end = begin + timedelta(microseconds=1)
            now = utcnow()
            filters: list[dict[str, Any]] = [
                {
                    "alias": "f1",
                    "source": n1.source,
                    "category": None,
                    "tags": [],
                    "from": begin.isoformat(),
                    "to": end.isoformat(),
                },
                {
                    "alias": "f2",
                    "source": n1.source,
                    "category": n1.category,
                    "tags": [n1.tags[0]],
                    "from": begin.isoformat(),
                    "to": end.isoformat(),
                },
                {
                    "alias": "f3",
                    "source": None,
                    "category": None,
                    "tags": [],
                    "from": (now + timedelta(days=365)).isoformat(),
                    "to": (now + timedelta(days=366)).isoformat(),
                },
            ]
            pools = []
            for data in filters:
                arguments = {key: value for key, value in data.items() if key != "alias"}
                result = await reader.call("search_news", {**arguments, "query": None, "limit": 5})
                if not isinstance(result, SearchResults) or len(result.items) >= 5:
                    raise AgentFailure("baseline_preparation_pool_incomplete")
                if bool(result.items) != (data["alias"] != "f3"):
                    raise AgentFailure("baseline_preparation_pool_expectation_failed")
                pools.append(result.items)
                for found in result.items:
                    if all(existing.id != found.id for existing in chosen):
                        detail = await reader.item(found.id)
                        if detail is None:
                            raise AgentFailure("baseline_preparation_item_disappeared")
                        chosen.append(detail)
            if len(chosen) > 9:
                raise AgentFailure("baseline_preparation_item_bound")
            aliases = {item.id: "n" + str(index) for index, item in enumerate(chosen, 1)}
            missing = uuid4()
            if await reader.item(missing) is not None:
                raise AgentFailure("baseline_preparation_missing_id_collision")
            items: list[dict[str, object]] = [
                {
                    "alias": aliases[item.id],
                    "item_id": str(item.id),
                    "present": True,
                    "fingerprint": fingerprint(item.model_dump(mode="json")),
                }
                for item in chosen
            ]
            items.append(
                {
                    "alias": "n_missing",
                    "item_id": str(missing),
                    "present": False,
                    "fingerprint": None,
                }
            )
            for data, pool in zip(filters, pools, strict=True):
                ordered = sorted(pool, key=lambda value: str(value.id))
                data["pool_aliases"] = [aliases[item.id] for item in ordered]
                data["pool_sha256"] = fingerprint(
                    [item.model_dump(mode="json", exclude={"similarity"}) for item in ordered]
                )
            fields = (
                "AZURE_ENV_NAME",
                "AZURE_SUBSCRIPTION_ID",
                "AZURE_RESOURCE_GROUP",
                "AGENT_TENANT_ID",
                "MODEL_ACCOUNT_ID",
                "MODEL_ENDPOINT",
                "ENRICHMENT_DEPLOYMENT",
                "ENRICHMENT_JOB_ID",
                "AGENT_EVALUATION_PROJECT_ID",
                "AGENT_EVALUATION_PROJECT_ENDPOINT",
                "AGENT_IMAGE",
                "AGENT_IMAGE_REVISION",
            )
            context = {key: env[key] for key in fields}
            context["operator"] = env["AGENT_EVALUATION_OPERATOR_PRINCIPAL_ID"]
            capture_fields = (
                "AGENT_TENANT_ID",
                "AGENT_API_CLIENT_ID",
                "MCP_API_CLIENT_ID",
                "MCP_RESOURCE_URL",
                "AGENT_PUBLIC_CLIENT_ID",
                "AGENT_RESOURCE_URL",
                "MCP_TENANT_ID",
                "MCP_PUBLIC_CLIENT_ID",
            )
            snapshot.save(
                "evidence/bindings-metadata.json",
                {
                    "actor_sha256": fingerprint(
                        {"oid": str(caller.object_id), "tenant": str(caller.tenant)}
                    ),
                    "context_sha256": fingerprint(context),
                    "capture_environment_sha256": fingerprint(
                        {key: env[key] for key in capture_fields}
                    ),
                    "items": items,
                    "filters": filters,
                    "model_calls": 0,
                    "observed_at": utcnow().isoformat(),
                },
            )
    snapshot.save(
        "evidence/status.json",
        {
            "outcome": "prepared",
            "model_calls": 0,
            "counts": snapshot.load("operations.json")["counts"],
        },
    )
    return {"outcome": "evidence_prepared", "items": len(items), "filters": 3, "model_calls": 0}


def run_previews(snapshot: Snapshot) -> dict[str, object]:
    from newsloom_platform import evaluation_verification as v

    snapshot.directory("previews")
    environment = {**os.environ, **AZD_AGENT}
    observed: dict[str, dict[str, int]] = {}
    for layer in LAYERS:
        owning = snapshot.root / OWNING[layer]
        cached = snapshot.root / ".azure/dev" / OWNING[layer] / "main.tfplan"
        snapshot.reserve("metadata_before")
        started = utcnow()
        result = run(
            ["azd", "provision", layer, "--preview", "--environment", "dev"],
            cwd=snapshot.root,
            env=environment,
            timeout=max(1.0, snapshot.require_window()),
            log=snapshot.base / "previews" / (layer + "-preview.log"),
        )
        if result.returncode:
            snapshot.save(
                f"previews/{layer}-failure.json",
                {
                    "outcome": "failed",
                    "exit_code": result.returncode,
                    "started_at": started.isoformat(),
                    "mutations": 0,
                    "model_calls": 0,
                },
            )
            raise PrepareFailure("baseline_readiness_owning_preview_failed")
        raw = read_private(cached)
        if cached.stat().st_mtime < started.timestamp():
            raise PrepareFailure("baseline_readiness_stale_cached_plan")
        v.binary_source(raw, owning)
        binary = snapshot.base / "previews" / (layer + ".tfplan")
        write_private(binary, raw)
        native = run(
            ["terraform", f"-chdir={owning}", "show", "-json", str(binary)],
            cwd=snapshot.root,
            timeout=max(1.0, min(60.0, snapshot.require_window())),
        )
        if native.returncode or len(native.stdout) > 16 * 1024 * 1024:
            raise PrepareFailure("baseline_readiness_native_plan_failed")
        plan = json.loads(native.stdout)
        snapshot.save(f"previews/{layer}-plan.json", plan)
        actions: dict[str, int] = {}
        for resource in plan.get("resource_changes", []):
            if resource.get("mode") == "managed":
                action = ",".join(resource["change"]["actions"])
                actions[action] = actions.get(action, 0) + 1
        snapshot.save(
            f"previews/{layer}-status.json",
            {
                "outcome": "preview_observed",
                "actions": actions,
                "binary_sha256": digest(raw),
                "native_sha256": v.digest(plan),
                "verified_at": utcnow().isoformat(),
                "mutations": 0,
                "model_calls": 0,
            },
        )
        if set(actions) != {"no-op"}:
            raise PrepareFailure("baseline_readiness_plan_not_noop")
        observed[layer] = actions
    return {"outcome": "previews_no_op", "actions": observed, "mutations": 0}


def verify_runtime(snapshot: Snapshot) -> dict[str, object]:
    from newsloom_platform import agent_control, control
    from newsloom_platform import evaluation_verification as v

    snapshot.reserve("metadata_before")
    response = run(
        AZD_VALUES,
        cwd=snapshot.root,
        env={**os.environ, **AZD_AGENT},
        timeout=max(1.0, min(30.0, snapshot.require_window())),
    )
    if response.returncode:
        raise PrepareFailure("baseline_runtime_context_failed")
    env = json.loads(response.stdout)
    if "@sha256:" not in env["AGENT_IMAGE"]:
        raise PrepareFailure("baseline_runtime_image_not_pinned")
    accepted = {
        "image_sha256": env["AGENT_IMAGE"].split("@sha256:", 1)[1],
        "source_sha256": env["AGENT_IMAGE_REVISION"],
    }
    reader = v.Reader(env, execution=False)
    native: object = None

    def exact_rest(url: str, category: str, **_: object) -> object:
        nonlocal native
        reader.guard(["rest", "--method", "get", "--url", url])
        if not url.startswith(v.ARM + env["AGENT_APP_ID"] + "?api-version="):
            raise PrepareFailure("baseline_runtime_foreign_read")
        snapshot.reserve("metadata_before")
        native = reader.cli(["rest", "--method", "get", "--url", url])
        return native

    original = control.rest
    control.rest = exact_rest
    try:
        agent_control.verify(env, "baseline-runtime-readiness")
    finally:
        control.rest = original
    if not isinstance(native, dict):
        raise PrepareFailure("baseline_runtime_missing_native_readback")
    evidence = {
        "outcome": "accepted_runtime_verified",
        "observed_at": utcnow().isoformat(),
        "image_sha256": accepted["image_sha256"],
        "source_sha256": accepted["source_sha256"],
        "observed_workload_sha256": v.workload_fingerprint(native),
        "model_calls": 0,
        "mutations": 0,
    }
    evidence_bytes = snapshot.save("runtime-evidence.json", evidence)
    accepted.update(
        {
            "configuration_sha256": evidence["observed_workload_sha256"],
            "receipt_sha256": digest(evidence_bytes),
        }
    )
    snapshot.save("runtime.json", {**evidence, "accepted_runtime": accepted})
    return {"outcome": "accepted_runtime_verified", "model_calls": 0, "mutations": 0}


def verify_prices(snapshot: Snapshot) -> dict[str, object]:
    import httpx

    rows: list[dict[str, Any]] = []
    url: str | None = PRICES_URL
    params: dict[str, str] | None = {
        "api-version": "2023-01-01-preview",
        "$filter": "armRegionName eq 'francecentral' and contains(productName, 'Azure OpenAI')",
    }
    with httpx.Client(trust_env=False, follow_redirects=False, timeout=30) as client:
        for _ in range(12):
            snapshot.require_window()
            destination = httpx.URL(url or "")
            if destination.scheme != "https" or destination.host != "prices.azure.com":
                raise PrepareFailure("baseline_prices_unexpected_endpoint")
            response = client.get(destination, params=params)
            response.raise_for_status()
            document = response.json()
            for row in document["Items"]:
                name = re.sub("[^a-z0-9]", "", (row["skuName"] + row["meterName"]).lower())
                if (
                    row["type"] == "Consumption"
                    and row["tierMinimumUnits"] == 0
                    and ("54mini" in name or "3large" in name)
                ):
                    rows.append(
                        {
                            key: row[key]
                            for key in (
                                "skuName",
                                "meterName",
                                "productName",
                                "armRegionName",
                                "currencyCode",
                                "unitOfMeasure",
                                "retailPrice",
                                "effectiveStartDate",
                            )
                        }
                    )
            url = document["NextPageLink"]
            if not url:
                break
            params = None
        else:
            raise PrepareFailure("baseline_prices_page_limit")
    selected = {}
    for sku in CHAT_SKUS:
        matches = [row for row in rows if row["skuName"] == sku]
        if (
            len(matches) != 1
            or matches[0]["currencyCode"] != "USD"
            or matches[0]["unitOfMeasure"] != "1M"
        ):
            raise PrepareFailure("baseline_prices_chat_meter_ambiguous")
        selected[sku] = matches[0]["retailPrice"]
    embedding = [row for row in rows if row["skuName"] == "text-embedding-3-large-regional"]
    if (
        len(embedding) != 1
        or embedding[0]["currencyCode"] != "USD"
        or embedding[0]["unitOfMeasure"] != "1K"
    ):
        raise PrepareFailure("baseline_prices_embedding_meter_missing")
    snapshot.require_window()
    result = {
        "verified_utc": utcnow().isoformat(),
        "source": PRICES_URL,
        "region": "francecentral",
        "currency": "USD",
        "chat_prices_per_million": selected,
        "embedding_meters": embedding,
        "all_matching_meters": rows,
    }
    snapshot.save("prices.json", result, indent=2)
    return {"outcome": "prices_verified", "chat_prices_per_million": selected}


def _exists(snapshot: Snapshot, relative: str) -> bool:
    return (snapshot.base / relative).is_file()


def previews_complete(snapshot: Snapshot) -> bool:
    for layer in LAYERS:
        try:
            status = snapshot.load(f"previews/{layer}-status.json")
        except FileNotFoundError:
            return False
        if set(status["actions"]) != {"no-op"} or not _exists(
            snapshot, f"previews/{layer}-plan.json"
        ):
            return False
    return True


@dataclass(frozen=True)
class Step:
    name: str
    partial: str
    complete: Callable[[Snapshot], bool]
    action: Callable[[Snapshot], dict[str, object]]


def steps() -> Iterator[Step]:
    yield Step(
        "metadata",
        "observations",
        lambda snapshot: _exists(snapshot, "observations/context-status.json"),
        observe_metadata,
    )
    yield Step(
        "evidence",
        "evidence",
        lambda snapshot: _exists(snapshot, "evidence/status.json"),
        prepare_evidence,
    )
    yield Step("previews", "previews", previews_complete, run_previews)
    yield Step(
        "runtime",
        "runtime-evidence.json",
        lambda snapshot: _exists(snapshot, "runtime.json"),
        verify_runtime,
    )
    yield Step(
        "prices", "prices.json", lambda snapshot: _exists(snapshot, "prices.json"), verify_prices
    )


def readiness(snapshot: Snapshot) -> dict[str, object]:
    snapshot.require_window()
    outcomes: dict[str, object] = {}
    rotated: list[str] = []
    for step in steps():
        snapshot.require_window()
        if step.complete(snapshot):
            outcomes[step.name] = "already_complete"
            continue
        moved = snapshot.rotate(step.partial)
        if moved is not None:
            rotated.append(moved)
        try:
            result = step.action(snapshot)
        except PrepareFailure, AgentFailure, PlatformFailure:
            raise
        except Exception:
            raise PrepareFailure(f"baseline_readiness_{step.name}_failed") from None
        outcomes[step.name] = result["outcome"]
        emit({"step": step.name, **result})
    return {
        "outcome": "readiness_prepared",
        "steps": outcomes,
        "rotated": rotated,
        "counts": snapshot.load("operations.json")["counts"],
        "model_calls": 0,
        "mutations": 0,
    }


# freeze / approve (evaluator venv)


def evaluator(snapshot: Snapshot, arguments: list[str]) -> dict[str, object]:
    environment = {
        key: value for key, value in os.environ.items() if key not in ("PYTHONPATH", "PYTHONHOME")
    }
    project = snapshot.root / EVALUATOR
    result = run(
        [str(project / ".venv/bin/python"), str(snapshot.root / HELPER), *arguments],
        cwd=project,
        env=environment,
        timeout=600,
    )
    lines = result.stdout.decode(errors="replace").strip().splitlines()
    try:
        document = json.loads(lines[-1])
    except IndexError, ValueError:
        document = None
    if not isinstance(document, dict):
        raise PrepareFailure(f"baseline_{arguments[0]}_failed")
    if result.returncode or document.get("outcome") == "failure":
        category = document.get("category")
        raise PrepareFailure(
            category
            if isinstance(category, str) and re.fullmatch(r"[a-z0-9_]{1,96}", category)
            else f"baseline_{arguments[0]}_failed"
        )
    return document


def freeze(snapshot: Snapshot) -> dict[str, object]:
    required = (
        "runtime.json",
        "prices.json",
        "operations.json",
        "prior-history.json",
        "evidence/bindings-metadata.json",
        "observations/scoped-before.json",
    )
    if not all(_exists(snapshot, name) for name in required) or not previews_complete(snapshot):
        raise PrepareFailure("baseline_freeze_readiness_incomplete")
    frozen = snapshot.base / FROZEN
    if (frozen / "execution-approval.json").exists():
        raise PrepareFailure("baseline_freeze_exists")
    # A freeze that failed before approval left a partial folder; keep it aside.
    if frozen.exists():
        snapshot.rotate(FROZEN)
    return evaluator(snapshot, ["freeze", "--state", str(snapshot.base)])


def approve(snapshot: Snapshot, instruction: str, reuse: Path | None) -> dict[str, object]:
    arguments = ["approve", "--state", str(snapshot.base), "--instruction", instruction]
    if reuse is not None:
        if not reuse.is_file() or reuse.is_symlink():
            raise PrepareFailure("baseline_calibration_reuse_invalid")
        data = read_private(reuse)
        if not data or len(data) > MAX_REUSED_CALIBRATION:
            raise PrepareFailure("baseline_calibration_reuse_invalid")
        arguments += ["--calibration-reuse-sha256", digest(data)]
    return evaluator(snapshot, arguments)


# record-usage


def _money(value: object) -> Decimal:
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        raise PrepareFailure("baseline_usage_amount_invalid") from None
    if not amount.is_finite() or amount < 0:
        raise PrepareFailure("baseline_usage_amount_invalid")
    return amount


def record_usage(snapshot: Snapshot, run_directory: Path) -> dict[str, object]:
    budget_bytes = read_private(run_directory / "budget.json")
    progress_bytes = read_private(run_directory / "partial-results.json")
    previous_bytes = snapshot.read("prior-history.json")
    budget, progress = json.loads(budget_bytes), json.loads(progress_bytes)
    previous = json.loads(previous_bytes)["estimated_usd"]
    if budget.get("halted") is not True:
        raise PrepareFailure("baseline_usage_run_not_halted")
    old_observed = _money(previous["total_observed_chat"])
    old_reserved = _money(previous["total_unmeasured_reserved"])
    carried = _money(previous["conservative_combined_exposure"])
    if (
        old_observed + old_reserved != carried
        or _money(budget.get("prior_model_exposure_usd", "0")) != carried
    ):
        raise PrepareFailure("baseline_usage_prior_mismatch")
    agents = budget["agents"]
    agent_observed = sum(
        (
            _money(row["observed_chat_usd"])
            for row in agents
            if row["observed_chat_usd"] is not None
        ),
        Decimal(0),
    )
    agent_unknown = sum(
        (_money(row["reserved_chat_usd"]) for row in agents if row["observed_chat_usd"] is None),
        Decimal(0),
    )
    embedding = _money(budget["operator_embedding_usd_reserved"]) + sum(
        (
            _money(row["reserved_embedding_usd"])
            for row in agents
            if not row["embedding_unused_verified"]
        ),
        Decimal(0),
    )
    judge = budget["judge"]
    judge_observed = _money(judge["estimated_observed_usd"])
    judge_unknown = _money(judge["estimated_reserved_unknown_usd"])
    new_observed = judge_observed + agent_observed
    new_unknown = judge_unknown + agent_unknown + embedding
    combined = _money(budget["combined_exposure_usd"])
    if old_observed + old_reserved + new_observed + new_unknown != combined:
        raise PrepareFailure("baseline_usage_exposure_mismatch")
    receipts = [row["receipt"] for row in agents if row["receipt"] is not None]
    controls = progress.get("controls", [])
    report = {
        "outcome": "baseline_run_halted_usage_recorded",
        "recorded_at": utcnow().isoformat(),
        "limit_profile": budget["limit_profile"],
        "run_state": progress.get("state"),
        "calibration_controls_passed": sum(1 for row in controls if row.get("passed")),
        "judge_attempts": judge["attempts"],
        "judge_transport_retries": judge["transport_retries"],
        "judge_input_tokens": judge["input_tokens_observed"],
        "judge_output_tokens": judge["output_tokens_observed"],
        "live_requests": len(agents),
        "live_completed": len(receipts),
        "agent_input_tokens": sum(row["input_tokens"] for row in receipts),
        "agent_output_tokens": sum(row["output_tokens"] for row in receipts),
        "semantic_scores": len(progress.get("scores", [])),
        "publication_creates": budget["counts"]["publication_creates"],
        "counts": budget["counts"],
        "estimated_usd": {
            "prior_observed_chat": str(old_observed),
            "prior_unmeasured_reserved": str(old_reserved),
            "run_observed_chat": str(new_observed),
            "run_unknown_judge_reserved": str(judge_unknown),
            "run_unknown_agent_chat_reserved": str(agent_unknown),
            "run_unattributed_embedding_reserved": str(embedding),
            "total_observed_chat": str(old_observed + new_observed),
            "total_unmeasured_reserved": str(old_reserved + new_unknown),
            "conservative_combined_exposure": budget["combined_exposure_usd"],
        },
        "interpretation": (
            "Price-based chat estimate and unmeasured reservations; not an Azure invoice."
        ),
        "original_deadline": budget["original_expires_at"],
        "approval_sha256": budget["approval_sha256"],
        "budget_receipt_sha256": digest(budget_bytes),
        "progress_receipt_sha256": digest(progress_bytes),
        "previous_usage_sha256": digest(previous_bytes),
        "old_run_replayed": False,
    }
    snapshot.save("usage-report.json", report, indent=2)
    return {
        "outcome": report["outcome"],
        "report": str((STATE / snapshot.name / "usage-report.json").as_posix()),
        "estimated_usd": report["estimated_usd"],
    }


# command line


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Prepare an agent-quality baseline snapshot.")
    commands = result.add_subparsers(dest="command", required=True)
    begin = commands.add_parser("start", help="open the 30-minute readiness window")
    begin.add_argument("--snapshot", required=True)
    begin.add_argument("--prior-usage", type=Path, required=True)
    begin.add_argument("--prior-run", type=Path, required=True)
    begin.add_argument("--instruction", required=True)
    ready = commands.add_parser("readiness", help="metadata, evidence, previews, runtime, prices")
    ready.add_argument("--snapshot", required=True)
    frozen = commands.add_parser("freeze", help="freeze inputs with the evaluator venv")
    frozen.add_argument("--snapshot", required=True)
    approval = commands.add_parser("approve", help="record the explicit execution approval")
    approval.add_argument("--snapshot", required=True)
    approval.add_argument("--instruction", required=True)
    approval.add_argument("--reuse-calibration", type=Path)
    usage = commands.add_parser("record-usage", help="record a stopped run as prior usage")
    usage.add_argument("--snapshot", required=True)
    usage.add_argument("--run", type=Path, required=True)
    return result


def dispatch(arguments: argparse.Namespace) -> dict[str, object]:
    snapshot = snapshot_for(arguments.snapshot)
    match arguments.command:
        case "start":
            return start(
                snapshot, arguments.prior_usage, arguments.prior_run, arguments.instruction
            )
        case "readiness":
            return readiness(snapshot)
        case "freeze":
            return freeze(snapshot)
        case "approve":
            return approve(snapshot, arguments.instruction, arguments.reuse_calibration)
        case _:
            return record_usage(snapshot, arguments.run)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        result = dispatch(arguments)
    except (PrepareFailure, AgentFailure, PlatformFailure) as error:
        category = str(error)
    except Exception:
        category = "baseline_{}_failed".format(arguments.command.replace("-", "_"))
    else:
        emit(result)
        return 0
    emit({"outcome": "failure", "category": category})
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
