"""Evaluator-venv half of ``scripts/baseline_prepare.py``: freeze and approve a snapshot.

Run only by ``baseline_prepare.py`` with ``tools/agent-evaluation/.venv/bin/python`` and
working directory ``tools/agent-evaluation``. It uses the standard library plus the
evaluator package and makes no network, Azure or model call. Output is metadata-only JSON.
"""

import argparse
import hashlib
import importlib
import json
import os
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

PROFILE = "baseline-14x10-v9"
SUITE = "v2"
SNAPSHOT_VERSION = 4
FROZEN = "frozen-v4"
LAYERS = ("application", "agent", "agent-evaluation")
FOUNDATION_ARCHIVE_COMMIT = "95570c48fa7bf7a16e2778be7d49d938a2fd9ea5"
APPROVAL_LIFETIME = timedelta(hours=3)
EVALUATOR = Path(__file__).resolve().parents[1] / "tools/agent-evaluation"


class StepFailure(Exception):
    """A fixed metadata-only category."""


def write_private(path: Path, data: bytes) -> bytes:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    return data


def save(path: Path, value: object) -> bytes:
    return write_private(path, json.dumps(value, sort_keys=True, allow_nan=False).encode())


def load(path: Path) -> Any:
    return json.loads(path.read_bytes())


def load_api() -> Any:
    sys.path.insert(0, str(EVALUATOR))
    admission = importlib.import_module("agent_evaluation.baseline_admission")
    budget = importlib.import_module("agent_evaluation.baseline_budget")
    inputs = importlib.import_module("agent_evaluation.baseline_inputs")
    provenance = importlib.import_module("agent_evaluation.baseline_provenance")
    policy = importlib.import_module("agent_evaluation.policy")
    return SimpleNamespace(
        ReadinessReceipt=admission.ReadinessReceipt,
        admit_native_plan=admission.admit_native_plan,
        infrastructure_digest=admission.infrastructure_digest,
        BaselineApproval=budget.BaselineApproval,
        OperationCounts=budget.OperationCounts,
        FrozenBaseline=inputs.FrozenBaseline,
        Oracles=inputs.Oracles,
        PrivateBindings=inputs.PrivateBindings,
        load_fixture_v2=inputs.load_fixture_v2,
        suite_digest=inputs.suite_digest,
        parse_document=inputs.parse_document,
        AcceptedRuntime=provenance.AcceptedRuntime,
        BaselineProvenance=provenance.BaselineProvenance,
        capture_source_digest=provenance.capture_source_digest,
        document_digest=provenance.document_digest,
        evaluator_source_digest=provenance.evaluator_source_digest,
        verify_production_inputs=provenance.verify_production_inputs,
        EvaluationFailure=policy.EvaluationFailure,
    )


def freeze(base: Path, api: Any, now: Callable[[], datetime]) -> dict[str, object]:
    target = base / FROZEN
    if target.exists() or target.is_symlink():
        raise StepFailure("baseline_freeze_exists")
    actual = load(base / "evidence/bindings-metadata.json")
    verified = load(base / "runtime.json")
    target.mkdir(mode=0o700)
    runtime = api.AcceptedRuntime.model_validate(verified["accepted_runtime"])
    fixture = api.load_fixture_v2()
    fixture_hash = api.suite_digest(SUITE)
    bindings = api.PrivateBindings.model_validate_json(
        json.dumps(
            {
                "schema_version": 1,
                "fixture_sha256": fixture_hash,
                "actor_sha256": actual["actor_sha256"],
                "context_sha256": actual["context_sha256"],
                "accepted_runtime": runtime.model_dump(mode="json"),
                "items": actual["items"],
                "filters": actual["filters"],
            }
        )
    )
    pools = {row.alias: row.pool_aliases for row in bindings.filters}
    items = {row.alias: row for row in bindings.items}
    binding_hash = api.document_digest(bindings.model_dump(mode="json", by_alias=True))
    oracles = api.Oracles.model_validate_json(
        json.dumps(
            {
                "schema_version": 1,
                "fixture_sha256": fixture_hash,
                "bindings_sha256": binding_hash,
                "cases": [
                    {
                        "case_id": row.case_id,
                        "expected_outcome": row.expected_outcome,
                        "expected_coverage": row.expected_coverage,
                        "required_aliases": [
                            alias
                            for alias in (
                                row.item_aliases
                                if row.filter_alias is None
                                else pools[row.filter_alias]
                            )
                            if items[alias].present and row.expected_outcome != "denied"
                        ],
                        "minimum_claims": 2
                        if row.case_id in ("b02", "b14")
                        else int(row.expected_outcome not in ("no_match", "denied")),
                        "expected_http_status": 401 if row.expected_outcome == "denied" else 200,
                    }
                    for row in fixture.cases
                ],
            }
        )
    )
    provenance = api.BaselineProvenance(
        schema_version=1,
        protocol="baseline-v1",
        foundation_archive_commit=FOUNDATION_ARCHIVE_COMMIT,
        accepted_runtime=runtime,
        evaluator_source_sha256=api.evaluator_source_digest(SUITE),
        capture_source_sha256=api.capture_source_digest(),
        production_inputs_sha256=api.verify_production_inputs(),
        fixture_sha256=fixture_hash,
        bindings_sha256=binding_hash,
        oracle_sha256=api.document_digest(oracles.model_dump(mode="json")),
        suite_version=SUITE,
    )
    frozen = api.FrozenBaseline(
        provenance=provenance,
        protocol="baseline-v1",
        bindings=bindings,
        oracles=oracles,
        snapshot_version=SNAPSHOT_VERSION,
        suite_version=SUITE,
    )
    frozen_document = frozen.model_dump(mode="json", by_alias=True)
    frozen_bytes = save(target / "frozen.json", frozen_document)
    layers = []
    bundle = {}
    for layer in LAYERS:
        plan = load(base / "previews" / (layer + "-plan.json"))
        retained = {
            row["address"]: row["values"]
            for row in plan["prior_state"]["values"]["root_module"]["resources"]
            if row["mode"] == "managed"
        }
        layers.append(
            api.admit_native_plan(
                plan, retained, layer, reviewed_at=now(), image_sha256=runtime.image_sha256
            )
        )
        bundle[layer] = {"plan": plan, "retained": retained}
    save(target / "no-change-plans.json", bundle)
    observed = load(base / "observations/scoped-before.json")
    readiness = api.ReadinessReceipt(
        protocol="baseline-readiness-v1",
        observed_at=now(),
        context_sha256=bindings.context_sha256,
        capture_environment_sha256=actual["capture_environment_sha256"],
        evaluator_source_sha256=provenance.evaluator_source_sha256,
        capture_source_sha256=provenance.capture_source_sha256,
        production_inputs_sha256=provenance.production_inputs_sha256,
        infrastructure_source_sha256=api.infrastructure_digest(),
        runtime_receipt_sha256=runtime.receipt_sha256,
        image_sha256=runtime.image_sha256,
        configuration_sha256=runtime.configuration_sha256,
        scoped_before_sha256=api.document_digest(observed),
        layers=(layers[0], layers[1], layers[2]),
    )
    readiness_bytes = save(target / "readiness.json", readiness.model_dump(mode="json"))
    operations = load(base / "operations.json")
    counts = api.OperationCounts.model_validate(
        {**api.OperationCounts.empty().model_dump(), **operations["counts"]}
    )
    prices = load(base / "prices.json")
    chat = prices["chat_prices_per_million"]
    input_price = Decimal(str(chat["5.4 mini Inp Dz"]))
    output_price = Decimal(str(chat["5.4 mini Opt Dz"]))
    embedding = Decimal(str(prices["embedding_meters"][0]["retailPrice"])) * 1000
    per_agent = input_price * 262144 / 1000000 + output_price * 4096 / 1000000
    embedding_reserve = embedding * 768 * 8192 / 1000000
    judge_reserve = input_price * 400000 / 1000000 + output_price * 1024 / 1000000
    prior_bytes = (base / "prior-history.json").read_bytes()
    prior_exposure = Decimal(
        json.loads(prior_bytes)["estimated_usd"]["conservative_combined_exposure"]
    )
    summary = {
        "outcome": "frozen_not_executed",
        "protocol": "baseline-v1",
        "snapshot_version": SNAPSHOT_VERSION,
        "suite_version": SUITE,
        "limit_profile": PROFILE,
        "cases": 14,
        "controls": 10,
        "score_rows": 34,
        "eligibility": {"faithfulness": 10, "citation_validity": 10, "contract_adherence": 14},
        "judge_attempt_limit": 96,
        "judge_transport_retries": 16,
        "thresholds": fixture.thresholds.model_dump(mode="json"),
        "frozen_sha256": api.document_digest(frozen_document),
        "frozen_file_sha256": hashlib.sha256(frozen_bytes).hexdigest(),
        "readiness_receipt_sha256": hashlib.sha256(readiness_bytes).hexdigest(),
        "evaluator_source_sha256": provenance.evaluator_source_sha256,
        "capture_source_sha256": provenance.capture_source_sha256,
        "preparation_counts": counts.model_dump(),
        "preparation_evidence_bytes": operations["evidence_response_bytes"],
        "prices_verified_at": prices["verified_utc"],
        "input_per_million_usd": str(chat["5.4 mini Inp Dz"]),
        "output_per_million_usd": str(chat["5.4 mini Opt Dz"]),
        "embedding_input_per_million_usd": str(embedding),
        "agent_full_request_reservation_usd": str(per_agent),
        "maximum_embedding_reservation_usd": str(embedding_reserve),
        "one_judge_attempt_reservation_usd": str(judge_reserve),
        "all_agent_plus_embedding_plus_one_judge_usd": str(
            per_agent * 14 + embedding_reserve + judge_reserve
        ),
        "maximum_usd": "100",
        "model_calls": 0,
        "uploads": 0,
        "prior_usage_sha256": hashlib.sha256(prior_bytes).hexdigest(),
        "prior_model_exposure_usd": str(prior_exposure),
        "initial_new_plus_carried_reservation_usd": str(
            prior_exposure + per_agent * 14 + embedding_reserve + judge_reserve
        ),
        "auth_limit": 40,
        "sign_in_limit": 9,
        "metadata_before_limit": 180,
        "metadata_after_limit": 60,
        "manual_report_retention_days": 30,
    }
    save(target / "admission-summary.json", summary)
    return summary


def approve(
    base: Path,
    api: Any,
    instruction: str,
    calibration_reuse_sha256: str | None,
    now: Callable[[], datetime],
) -> dict[str, object]:
    target = base / FROZEN
    summary = load(target / "admission-summary.json")
    if summary.get("limit_profile") != PROFILE:
        raise StepFailure("baseline_approval_profile_mismatch")
    frozen = api.parse_document(api.FrozenBaseline, (target / "frozen.json").read_bytes())
    readiness = api.parse_document(api.ReadinessReceipt, (target / "readiness.json").read_bytes())
    moment = now()
    readiness.verify(frozen, moment)
    optional = (
        {}
        if calibration_reuse_sha256 is None
        else {"calibration_reuse_sha256": calibration_reuse_sha256}
    )
    approval = api.BaselineApproval(
        schema_version=1,
        protocol="baseline-v1",
        limit_profile=PROFILE,
        execution_approved=True,
        frozen_sha256=summary["frozen_sha256"],
        readiness_receipt_sha256=summary["readiness_receipt_sha256"],
        approved_at=moment,
        expires_at=moment + APPROVAL_LIFETIME,
        prices_verified_at=datetime.fromisoformat(summary["prices_verified_at"]),
        input_per_million_usd=summary["input_per_million_usd"],
        output_per_million_usd=summary["output_per_million_usd"],
        embedding_input_per_million_usd=summary["embedding_input_per_million_usd"],
        embedding_token_bound=8192,
        maximum_usd="100",
        preparation_counts=api.OperationCounts.model_validate(summary["preparation_counts"]),
        preparation_evidence_bytes=summary["preparation_evidence_bytes"],
        preparation_ipc_sent_bytes=0,
        preparation_ipc_received_bytes=0,
        preparation_model_calls=0,
        prior_usage_sha256=summary["prior_usage_sha256"],
        prior_model_exposure_usd=summary["prior_model_exposure_usd"],
        **optional,
    )
    approval.validate_execution(moment, frozen)
    raw = write_private(target / "execution-approval.json", approval.model_dump_json().encode())
    authorization: dict[str, object] = {
        "user_instruction": instruction,
        "maximum_cumulative_usd": "100",
        "snapshot_version": SNAPSHOT_VERSION,
        "limit_profile": PROFILE,
        "frozen_sha256": approval.frozen_sha256,
        "approval_sha256": hashlib.sha256(raw).hexdigest(),
        "prior_usage_sha256": approval.prior_usage_sha256,
        "prior_model_exposure_usd": approval.prior_model_exposure_usd,
        "approved_at": moment.isoformat(),
        "expires_at": approval.expires_at.isoformat(),
        "old_run_or_deadline_modified": False,
        "criteria_or_fixture_repaired": False,
        "new_resource_or_permission_scope": False,
        **optional,
    }
    save(target / "execution-authorization.json", authorization)
    return authorization


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    frozen = commands.add_parser("freeze")
    frozen.add_argument("--state", type=Path, required=True)
    approval = commands.add_parser("approve")
    approval.add_argument("--state", type=Path, required=True)
    approval.add_argument("--instruction", required=True)
    approval.add_argument("--calibration-reuse-sha256")
    return result


def main(argv: Sequence[str] | None = None, api: Any = None) -> int:
    arguments = parser().parse_args(argv)
    category = f"baseline_{arguments.command}_failed"
    try:
        api = load_api() if api is None else api
        if arguments.command == "freeze":
            result = freeze(arguments.state, api, lambda: datetime.now(UTC))
        else:
            result = approve(
                arguments.state,
                api,
                arguments.instruction,
                arguments.calibration_reuse_sha256,
                lambda: datetime.now(UTC),
            )
    except StepFailure as error:
        category = str(error)
    except Exception as error:
        if api is not None and isinstance(error, api.EvaluationFailure):
            category = str(error)
    else:
        print(json.dumps(result, sort_keys=True))
        return 0
    print(json.dumps({"outcome": "failure", "category": category}))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
