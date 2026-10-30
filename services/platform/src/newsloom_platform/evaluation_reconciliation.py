"""Audited reconciliation of the one retained, failed parent verification."""

import base64
import hashlib
import io
import json
import re
import subprocess
import tempfile
import time
import zlib
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from zipfile import ZipFile

from pydantic import BaseModel, ConfigDict, Field, model_validator

from newsloom_platform import agent_evaluation, control, evaluation_record_probe
from newsloom_platform import evaluation_verification as v
from newsloom_platform.config import PlatformFailure, json_object, text_field
from newsloom_platform.events import event

FEATURE = "Microsoft.CognitiveServices/CostControls"
TRANSITION_FILES = {
    "services/platform/src/newsloom_platform/agent_evaluation.py",
    "services/platform/src/newsloom_platform/evaluation_verification.py",
    "services/platform/src/newsloom_platform/evaluation_reconciliation.py",
    "services/platform/src/newsloom_platform/evaluation_record_probe.py",
    "services/platform/src/newsloom_platform/cli.py",
    "tools/agent-evaluation/agent_evaluation/context.py",
    "tools/agent-evaluation/tests/test_context.py",
}


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)

    action: Literal["execute-records", "verify"]
    output: str
    preservation: str
    source_archive: str
    evidence_archive: str
    baseline: str
    review: str
    plan: str
    approval: str
    intent: str
    completion: str
    failure: str
    account_before: str
    account_after: str
    probe: str | None = None
    state_repair: str | None = None

    @model_validator(mode="after")
    def boundary(self) -> Manifest:
        if (self.action == "verify") != (self.probe is not None):
            raise ValueError("Only verification accepts completed execution evidence.")
        return self


class Records(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)

    record_schema: Literal["news-metadata-v1"] = Field(alias="schema")
    outcome: Literal["success"]
    verified_utc: str
    news_count: int
    rows: list[list[str]]
    historical_membership: list[int]
    reconstructions: list[dict[str, object]]
    read_only: bool
    identity_sha256: str
    statement_timeout_ms: int
    transaction_timeout_ms: int
    elapsed_ms: int
    writes_performed: int
    model_calls: int


def records(value: dict[str, object], *, fresh: bool = True) -> dict[str, str]:
    parsed = Records.model_validate(value)
    if (
        not parsed.read_only
        or parsed.statement_timeout_ms != 60000
        or parsed.transaction_timeout_ms != 540000
        or not 0 <= parsed.elapsed_ms < 570000
        or parsed.writes_performed != 0
        or parsed.model_calls != 0
        or not 0 < parsed.news_count <= evaluation_record_probe.MAX_ROWS
        or len(parsed.rows) != parsed.news_count
        or len(evaluation_record_probe.encoded(value)) > evaluation_record_probe.MAX_BYTES
        or parsed.rows != sorted(parsed.rows)
        or any(len(row) != 2 for row in parsed.rows)
    ):
        raise PlatformFailure("evaluation_reconciliation_incomplete_record_evidence")
    v.fingerprint(parsed.identity_sha256)
    result = {v.fingerprint(row[0]): v.fingerprint(row[1]) for row in parsed.rows}
    if len(result) != parsed.news_count:
        raise PlatformFailure("evaluation_reconciliation_duplicate_record")
    if parsed.historical_membership or parsed.reconstructions:
        if (
            len(parsed.historical_membership) != parsed.news_count
            or any(stage not in (0, 1, 2) for stage in parsed.historical_membership)
            or len(parsed.reconstructions) != 2
        ):
            raise PlatformFailure("evaluation_reconciliation_incomplete_record_evidence")
        for index, reconstruction in enumerate(parsed.reconstructions):
            if (
                set(reconstruction)
                != {
                    "cutoff_utc",
                    "news_count",
                    "news_metadata_fingerprint",
                    "recent_id_sha256",
                    "recent_url_sha256",
                }
                or type(reconstruction["news_count"]) is not int
                or reconstruction["news_count"]
                != sum(stage <= index for stage in parsed.historical_membership)
            ):
                raise PlatformFailure("evaluation_reconciliation_incomplete_record_evidence")
            v.timestamp(reconstruction["cutoff_utc"])
            for key in ("news_metadata_fingerprint", "recent_id_sha256", "recent_url_sha256"):
                v.fingerprint(reconstruction[key])
    if fresh:
        v.fresh(parsed.verified_utc, 900)
    else:
        v.timestamp(parsed.verified_utc)
    return result


def appended(before: dict[str, object], after: dict[str, object]) -> list[str]:
    old, new = records(before, fresh=False), records(after)
    if v.timestamp(after.get("verified_utc")) <= v.timestamp(before.get("verified_utc")):
        raise PlatformFailure("evaluation_reconciliation_independent_records_required")
    if any(new.get(identifier) != fingerprint for identifier, fingerprint in old.items()):
        raise PlatformFailure("evaluation_reconciliation_original_record_changed")
    return sorted(new.keys() - old.keys())


def reconstructed(
    probe: dict[str, object],
    before: dict[str, object],
    failed: dict[str, object],
    *,
    fresh: bool = True,
) -> list[int]:
    records(probe, fresh=fresh)
    membership = probe["historical_membership"]
    if (
        not isinstance(membership, list)
        or len(membership) != probe["news_count"]
        or any(type(stage) is not int or stage not in (0, 1, 2) for stage in membership)
    ):
        raise PlatformFailure("evaluation_reconciliation_historical_membership_required")
    counts = [membership.count(stage) for stage in (0, 1, 2)]
    historical = v.rows(probe["reconstructions"])
    if len(historical) != 2:
        raise PlatformFailure("evaluation_reconciliation_historical_reconstruction_required")
    for index, original in enumerate((before, failed)):
        if (
            set(historical[index])
            != {
                "cutoff_utc",
                "news_count",
                "news_metadata_fingerprint",
                "recent_id_sha256",
                "recent_url_sha256",
            }
            or historical[index]["cutoff_utc"] != original["verified_utc"]
            or any(
                historical[index][key] != original[key]
                for key in (
                    "news_count",
                    "news_metadata_fingerprint",
                    "recent_id_sha256",
                    "recent_url_sha256",
                )
            )
            or historical[index]["news_count"] != sum(counts[: index + 1])
        ):
            raise PlatformFailure("evaluation_reconciliation_historical_fingerprint_mismatch")
    return counts


def metadata(
    before: dict[str, object],
    after: dict[str, object],
    env: dict[str, str],
    raw_before: dict[str, object],
    raw_after: dict[str, object],
    *,
    project_bookkeeping: bool = False,
) -> tuple[dict[str, object], dict[str, object]]:
    old, new = (v.scoped_snapshot(value, env, historical=True) for value in (before, after))
    original, current = v.account_invariant(raw_before), v.account_invariant(raw_after)
    if v.digest(original) != old["account"] or v.digest(current) != new["account"]:
        raise PlatformFailure("evaluation_reconciliation_account_preimage_mismatch")
    if project_bookkeeping:
        previous = json_object(original["properties"])
        properties = json_object(current["properties"])
        name = v.project_id(env).rsplit("/", 1)[-1]
        if (
            "associatedProjects" in previous
            or "defaultProject" in previous
            or properties.get("associatedProjects") != [name]
            or properties.get("defaultProject") != name
            or previous.get("armFeatures") != properties.get("armFeatures")
        ):
            raise PlatformFailure("evaluation_reconciliation_project_bookkeeping_mismatch")
        properties.pop("associatedProjects")
        properties.pop("defaultProject")
        current["properties"] = properties
        if current != original:
            raise PlatformFailure("evaluation_reconciliation_account_drift")
        new["account"] = old["account"]
    if old["account"] != new["account"]:
        properties = json_object(current["properties"])
        previous = json_object(original["properties"])
        if properties.get("armFeatures") != [FEATURE] or previous.get("armFeatures") is not None:
            raise PlatformFailure("evaluation_reconciliation_unreviewed_feature")
        if "armFeatures" in previous:
            properties["armFeatures"] = previous["armFeatures"]
        else:
            properties.pop("armFeatures")
        current["properties"] = properties
        if current != original:
            raise PlatformFailure("evaluation_reconciliation_account_drift")
        new["account"] = old["account"]
    return old, new


def source_transition(evidence: v.Evidence, manifest: Manifest) -> tuple[str, dict[str, str]]:
    preserved = evidence.document(manifest.preservation)
    raw = evidence.read(manifest.source_archive)
    if hashlib.sha256(raw).hexdigest() != preserved.get("source_archive_sha256"):
        raise PlatformFailure("evaluation_reconciliation_source_archive_mismatch")
    historical = json_object(preserved["source_files"])
    if any(
        Path(name).is_absolute() or ".." in Path(name).parts or (evidence.root / name).is_symlink()
        for name in historical
    ):
        raise PlatformFailure("evaluation_reconciliation_source_inventory")
    with ZipFile(io.BytesIO(raw)) as archive:
        if len(archive.namelist()) != len(historical) or set(archive.namelist()) != set(historical):
            raise PlatformFailure("evaluation_reconciliation_source_inventory")
        if sum(item.file_size for item in archive.infolist()) > v.MAX_BYTES:
            raise PlatformFailure("evaluation_reconciliation_archive_limit")
        for name, fingerprint in historical.items():
            if hashlib.sha256(archive.read(name)).hexdigest() != v.fingerprint(fingerprint):
                raise PlatformFailure("evaluation_reconciliation_source_preimage_mismatch")
    historical_source = v.digest(historical)
    if historical_source != preserved.get("historical_source_sha256"):
        raise PlatformFailure("evaluation_reconciliation_historical_source_mismatch")
    for name in historical.keys() - TRANSITION_FILES:
        path = evidence.root / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != historical[name]:
            raise PlatformFailure("evaluation_reconciliation_unreviewed_source_transition")
    current_source = v.source(evidence.root)
    # Inventory, not only old paths, is checked: no unrelated newly added source is admitted.
    current_paths = {
        path
        for path in control.run(
            [
                "git",
                "-C",
                str(evidence.root),
                "ls-files",
                "--cached",
                "--others",
                "--exclude-standard",
                "-z",
            ],
            "evaluation_reconciliation_source",
        ).split("\0")
        if path
        and (
            path.startswith(("infra/", "services/platform/", "tools/agent-evaluation/"))
            or path in historical
        )
    }
    if current_paths - historical.keys() - TRANSITION_FILES:
        raise PlatformFailure("evaluation_reconciliation_unreviewed_source_transition")
    if current_source == historical_source:
        raise PlatformFailure("evaluation_reconciliation_source_transition_required")
    return historical_source, {
        "historical_source_sha256": historical_source,
        "source_sha256": current_source,
        "preservation_sha256": hashlib.sha256(evidence.read(manifest.preservation)).hexdigest(),
    }


def chain(
    evidence: v.Evidence, manifest: Manifest, env: dict[str, str]
) -> tuple[dict[str, object], dict[str, object], dict[str, str]]:
    old_source, transition = source_transition(evidence, manifest)
    preserved = evidence.document(manifest.preservation)
    raw = evidence.read(manifest.evidence_archive)
    if hashlib.sha256(raw).hexdigest() != preserved.get("evidence_archive_sha256"):
        raise PlatformFailure("evaluation_reconciliation_evidence_archive_mismatch")
    retained = json_object(preserved["evidence_files"])
    names = ("baseline", "review", "plan", "approval", "intent", "completion", "failure")
    with ZipFile(io.BytesIO(raw)) as archive:
        if (
            len(archive.namelist()) != len(set(archive.namelist()))
            or sum(item.file_size for item in archive.infolist()) > v.MAX_BYTES
        ):
            raise PlatformFailure("evaluation_reconciliation_archive_limit")
        for key in names:
            path = getattr(manifest, key)
            name = evidence.path(path).name
            content = evidence.read(path)
            if (
                name not in archive.namelist()
                or archive.read(name) != content
                or retained.get(name) != hashlib.sha256(content).hexdigest()
            ):
                raise PlatformFailure("evaluation_reconciliation_original_evidence_changed")
    before, review, failure, approval, intent, completion = (
        evidence.document(getattr(manifest, key))
        for key in ("baseline", "review", "failure", "approval", "intent", "completion")
    )
    binding = {
        "context_sha256": v.context(env),
        "source_sha256": old_source,
        "layer": "application",
    }
    for value in (before, review, failure):
        if any(value.get(key) != expected for key, expected in binding.items()):
            raise PlatformFailure("evaluation_reconciliation_historical_binding_mismatch")
    baseline_hash = hashlib.sha256(evidence.read(manifest.baseline)).hexdigest()
    plan_hash = hashlib.sha256(evidence.read(manifest.plan)).hexdigest()
    if (
        before.get("mode") != "baseline"
        or before.get("outcome") != "success"
        or review.get("mode") != "plan"
        or review.get("outcome") != "success"
        or failure.get("mode") != "readback"
        or failure.get("outcome") != "failure"
        or failure.get("category") != "evaluation_verification_preservation_drift"
        or any(value.get("baseline_sha256") != baseline_hash for value in (review, failure))
        or any(value.get("plan_sha256") != plan_hash for value in (review, failure))
        or intent.get("approved_plan_sha256") != plan_hash
        or intent.get("source_sha256") != old_source
        or intent.get("layer") != "application"
        or intent.get("state_lock_enabled") is not True
        or intent.get("unknown_outcome_must_not_be_replayed") is not True
        or completion.get("azd_exit_code") != 0
        or completion.get("layer") != "application"
        or completion.get("independent_readback_still_required") is not True
        or approval.get("context_sha256") != binding["context_sha256"]
        or approval.get("source_sha256") != old_source
        or approval.get("user_response") != "approve_foundation_only"
        or approval.get("project_and_two_operator_assignments_approved") is not True
    ):
        raise PlatformFailure("evaluation_reconciliation_applied_lineage_mismatch")
    times = [
        v.timestamp(value[key])
        for value, key in (
            (before, "verified_utc"),
            (review, "verified_utc"),
            (approval, "recorded_utc"),
            (intent, "recorded_utc"),
            (completion, "completed_utc"),
            (failure, "verified_utc"),
            (preserved, "preserved_utc"),
        )
    ]
    ordered = [times[index] for index in (0, 1, 3, 4, 5, 6)]
    if (
        ordered != sorted(ordered)
        or not times[0] <= times[2] <= times[3]
        or not 0 <= times[3] - times[1] <= 3600
        or not 0 <= times[3] - times[2] <= 3600
    ):
        raise PlatformFailure("evaluation_reconciliation_historical_chronology")
    binary = evidence.read(manifest.plan)
    v.binary_source(binary, evidence.root / "infra")
    native = json_object(
        json.loads(
            control.run(
                [
                    "terraform",
                    f"-chdir={evidence.root / 'infra'}",
                    "show",
                    "-json",
                    str(evidence.path(manifest.plan)),
                ],
                "evaluation_reconciliation_native_plan",
                timeout=60,
            )
        )
    )
    inventory = v.verify_plan(native, env, "application", reviewed_at=times[1])
    if any(value.get("plan_inventory") != inventory for value in (review, failure)):
        raise PlatformFailure("evaluation_reconciliation_historical_plan_mismatch")
    v.retained_plan(native, json_object(before["snapshot"]), env, "application")
    transition["verification_scope_sha256"] = v.digest(v.verification_scope(env))
    if manifest.state_repair is not None:
        repair_source = v.fingerprint(evidence.document(manifest.state_repair).get("source_sha256"))
        validate_state_repair(evidence, manifest.state_repair, env, repair_source)
        transition["state_repair_source_sha256"] = repair_source
        transition["state_repair_sha256"] = hashlib.sha256(
            evidence.read(manifest.state_repair)
        ).hexdigest()
    return before, failure, transition


IDENTITY_OUTPUTS = {
    "MODEL_ACCOUNT_IDENTITY_PRINCIPAL_ID": "principal_id",
    "MODEL_ACCOUNT_IDENTITY_TENANT_ID": "tenant_id",
}


def state_output_plan(
    plan: dict[str, object],
    env: dict[str, str],
    *,
    reviewed_at: float | None = None,
) -> dict[str, object]:
    checked = deepcopy(plan)
    drift = v.rows(checked.get("resource_drift"))
    if len(drift) != 1 or drift[0].get("address") != "azurerm_cognitive_account.models":
        raise PlatformFailure("evaluation_reconciliation_state_drift_inventory")
    change = json_object(drift[0]["change"])
    before, after = (json_object(change[key]) for key in ("before", "after"))
    identities = v.rows(before.get("identity"))
    if (
        len(identities) != 1
        or identities[0].get("identity_ids") is not None
        or identities[0].get("type") != "SystemAssigned"
        or change.get("actions") != ["update"]
        or change.get("replace_paths")
        or change.get("importing")
    ):
        raise PlatformFailure("evaluation_reconciliation_state_identity_normalization")
    identities[0]["identity_ids"] = []
    before["identity"] = identities
    if before != after:
        raise PlatformFailure("evaluation_reconciliation_state_authority_drift")
    checked["resource_drift"] = []
    inventory = v.verify_plan(checked, env, "application", reviewed_at=reviewed_at)
    if inventory["mutations"] != 0:
        raise PlatformFailure("evaluation_reconciliation_state_resource_write")
    outputs = json_object(plan.get("output_changes"))
    changed = {
        key for key, value in outputs.items() if json_object(value).get("actions") != ["no-op"]
    }
    if changed != set(IDENTITY_OUTPUTS):
        raise PlatformFailure("evaluation_reconciliation_state_output_inventory")
    current = v.rows(after["identity"])[0]
    for output, field in IDENTITY_OUTPUTS.items():
        value = json_object(outputs[output])
        if (
            value.get("actions") != ["create"]
            or value.get("before") is not None
            or value.get("after") != current.get(field)
            or not isinstance(value.get("after"), str)
            or not value.get("after")
            or value.get("after_unknown") not in (False, {})
        ):
            raise PlatformFailure("evaluation_reconciliation_state_output_mismatch")
    return inventory


def canonical_state(value: dict[str, object]) -> dict[str, object]:
    result = deepcopy(value)
    if result.get("check_results") is None:
        return result
    checks = v.rows(result["check_results"])
    if len({text_field(check, "config_addr") for check in checks}) != len(checks):
        raise PlatformFailure("evaluation_reconciliation_duplicate_state_check")
    for check in checks:
        if check.get("objects") is None:
            continue
        objects = v.rows(check["objects"])
        if len({text_field(item, "object_addr") for item in objects}) != len(objects):
            raise PlatformFailure("evaluation_reconciliation_duplicate_state_check")
        check["objects"] = sorted(objects, key=lambda item: text_field(item, "object_addr"))
    result["check_results"] = sorted(checks, key=lambda check: text_field(check, "config_addr"))
    return result


def state_only_transition(before: dict[str, object], after: dict[str, object]) -> None:
    old, new = canonical_state(before), canonical_state(after)
    if (
        type(old.get("serial")) is not int
        or type(new.get("serial")) is not int
        or int(str(new["serial"])) <= int(str(old["serial"]))
        or old.get("lineage") != new.get("lineage")
    ):
        raise PlatformFailure("evaluation_reconciliation_state_lineage")
    old["serial"] = new["serial"]
    resources = v.rows(old.get("resources"))
    matches = [
        resource
        for resource in resources
        if resource.get("type") == "azurerm_cognitive_account" and resource.get("name") == "models"
    ]
    if len(matches) != 1:
        raise PlatformFailure("evaluation_reconciliation_state_account_inventory")
    instances = v.rows(matches[0].get("instances"))
    if len(instances) != 1:
        raise PlatformFailure("evaluation_reconciliation_state_account_inventory")
    attributes = json_object(instances[0]["attributes"])
    identities = v.rows(attributes["identity"])
    if len(identities) != 1 or identities[0].get("identity_ids") is not None:
        raise PlatformFailure("evaluation_reconciliation_state_identity_normalization")
    identities[0]["identity_ids"] = []
    attributes["identity"] = identities
    instances[0]["attributes"] = attributes
    matches[0]["instances"] = instances
    old["resources"] = resources
    outputs = json_object(old.get("outputs"))
    current_outputs = json_object(new.get("outputs"))
    if set(current_outputs) - outputs.keys() != set(IDENTITY_OUTPUTS):
        raise PlatformFailure("evaluation_reconciliation_state_output_inventory")
    for name in IDENTITY_OUTPUTS:
        outputs[name] = current_outputs[name]
    old["outputs"] = outputs
    if old != new:
        raise PlatformFailure("evaluation_reconciliation_unreviewed_state_write")


def validate_state_repair(
    evidence: v.Evidence,
    path: str,
    env: dict[str, str],
    source: str,
) -> None:
    value = evidence.document(path)
    if (
        value.get("source_sha256") != source
        or value.get("context_sha256") != v.context(env)
        or value.get("outcome") != "success"
        or value.get("resource_mutations") != 0
        or value.get("state_lock_enabled") is not True
        or value.get("azd_exit_code") != 0
    ):
        raise PlatformFailure("evaluation_reconciliation_state_repair_binding")
    for key in ("plan", "before_state", "after_state", "apply_intent"):
        if hashlib.sha256(evidence.read(text_field(value, key))).hexdigest() != value.get(
            key + "_sha256"
        ):
            raise PlatformFailure("evaluation_reconciliation_state_repair_evidence")
    intent = evidence.document(text_field(value, "apply_intent"))
    if (
        intent.get("source_sha256") != source
        or intent.get("context_sha256") != v.context(env)
        or intent.get("approved_plan_sha256") != value.get("plan_sha256")
        or intent.get("state_lock_enabled") is not True
        or intent.get("resource_mutations") != 0
        or intent.get("replay_prohibited") is not True
    ):
        raise PlatformFailure("evaluation_reconciliation_state_repair_intent")
    binary = evidence.read(text_field(value, "plan"))
    v.binary_source(binary, evidence.root / "infra")
    native = json_object(
        json.loads(
            control.run(
                [
                    "terraform",
                    f"-chdir={evidence.root / 'infra'}",
                    "show",
                    "-json",
                    str(evidence.path(text_field(value, "plan"))),
                ],
                "evaluation_reconciliation_state_plan",
                timeout=60,
            )
        )
    )
    state_output_plan(native, env, reviewed_at=v.timestamp(value["reviewed_utc"]))
    before = evidence.document(text_field(value, "before_state"))
    after = evidence.document(text_field(value, "after_state"))
    state_only_transition(before, after)
    outputs = json_object(after["outputs"])
    for name in IDENTITY_OUTPUTS:
        if json_object(outputs[name]).get("value") != env.get(name):
            raise PlatformFailure("evaluation_reconciliation_state_environment_outputs")


class AccountReader(v.Reader):
    def __init__(self, env: dict[str, str]):
        super().__init__(env)
        self.account_id = env["MODEL_ACCOUNT_ID"]
        self.account: dict[str, object] = {}

    def get(self, identifier: str, api: str = agent_evaluation.ARM_API) -> dict[str, object]:
        value = super().get(identifier, api)
        if identifier == self.account_id:
            self.account = value
        return value


def verify(env: dict[str, str], correlation: str, manifest_path: str) -> None:
    root = Path(control.run(["git", "rev-parse", "--show-toplevel"], "project_root"))
    evidence = v.Evidence(root, env["AZURE_ENV_NAME"])
    manifest = Manifest.model_validate(evidence.document(manifest_path))
    if evidence.path(manifest.output).exists():
        raise PlatformFailure("evaluation_reconciliation_output_already_exists")
    before, failure, transition = chain(evidence, manifest, env)
    reader = AccountReader(env)
    v.operator(reader, env)
    if manifest.action == "execute-records":
        execute_records(evidence, manifest, env, before, failure, transition)
        return
    assert manifest.probe is not None
    execution = evidence.document(manifest.probe)
    probe = json_object(execution.get("records"))
    validate_execution(evidence, env, before, failure, transition, execution)
    counts = reconstructed(
        probe,
        json_object(json_object(before["snapshot"])["stored_record"]),
        json_object(json_object(failure["snapshot"])["stored_record"]),
    )
    current = v.snapshot(reader, env)
    current["stored_record"] = probe
    raw_before = json_object(evidence.document(manifest.account_before).get("account"))
    raw_failed = json_object(evidence.document(manifest.account_after).get("after_account"))
    old = json_object(before["snapshot"])
    failed = json_object(failure["snapshot"])
    for after, raw in ((failed, raw_failed), (current, reader.account)):
        left, right = metadata(old, after, env, raw_before, raw)
        v.compare_authority(left, right, env, "application")
    if reader.calls > 100 or time.monotonic() > reader.deadline:
        raise PlatformFailure("evaluation_verification_metadata_limit")
    if v.source(root) != transition["source_sha256"]:
        raise PlatformFailure("evaluation_verification_source_changed")
    inputs = {
        key: {"path": value, "sha256": hashlib.sha256(evidence.read(value)).hexdigest()}
        for key, value in manifest.model_dump().items()
        if key not in ("action", "output") and isinstance(value, str)
    }
    evidence.write(
        manifest.output,
        {
            **transition,
            "context_sha256": v.context(env),
            "mode": "reconciliation",
            "layer": "application",
            "outcome": "success",
            "verified_utc": datetime.now(UTC).isoformat(),
            "inputs": inputs,
            "snapshot": current,
            "account_preimage": reader.account,
            "verification_scope": v.verification_scope(env),
            "original_count": counts[0],
            "failed_readback_additions": counts[1],
            "later_additions": counts[2],
            "metadata_reads": reader.calls,
            "verification_executions": 1,
            "resource_mutations": 0,
            "model_calls": 0,
        },
    )
    event(
        "agent_evaluation_reconciliation",
        "success",
        correlation,
        counts={
            "original_records": counts[0],
            "additions": counts[1] + counts[2],
            "model_calls": 0,
        },
    )


def parse_lines(output: str) -> dict[str, object]:
    if len(output.encode()) > evaluation_record_probe.MAX_BYTES:
        raise PlatformFailure("evaluation_reconciliation_output_limit")
    chunks: dict[int, str] = {}
    total: int | None = None
    fingerprint: str | None = None
    for line in output.splitlines():
        position = line.find(evaluation_record_probe.PREFIX)
        if position < 0:
            continue
        value = json_object(json.loads(line[position + len(evaluation_record_probe.PREFIX) :]))
        if set(value) != {"index", "total", "sha256", "payload"}:
            raise PlatformFailure("evaluation_reconciliation_probe_failed")
        index, count = value["index"], value["total"]
        if (
            type(index) is not int
            or type(count) is not int
            or not 0 <= index < count <= 128
            or index in chunks
            or (total is not None and count != total)
            or (fingerprint is not None and fingerprint != value["sha256"])
        ):
            raise PlatformFailure("evaluation_reconciliation_partial_probe")
        total, fingerprint = count, v.fingerprint(value["sha256"])
        chunks[index] = text_field(value, "payload")
    if total is None or len(chunks) != total:
        raise PlatformFailure("evaluation_reconciliation_partial_probe")
    decoder = zlib.decompressobj()
    decoded = decoder.decompress(
        base64.b64decode("".join(chunks[index] for index in range(total)), validate=True),
        evaluation_record_probe.MAX_BYTES + 1,
    )
    if (
        len(decoded) > evaluation_record_probe.MAX_BYTES
        or not decoder.eof
        or decoder.unused_data
        or hashlib.sha256(decoded).hexdigest() != fingerprint
    ):
        raise PlatformFailure("evaluation_reconciliation_probe_digest_mismatch")
    result = json_object(json.loads(decoded))
    records(result)
    return result


def job_boundary(
    job: dict[str, object], env: dict[str, str], before: dict[str, object]
) -> dict[str, object]:
    expected = json_object(json_object(before["snapshot"])["workloads"]).get(
        env["MIGRATION_JOB_ID"]
    )
    properties = json_object(job.get("properties"))
    configuration = json_object(properties.get("configuration"))
    template = json_object(properties.get("template"))
    containers = v.rows(template.get("containers"))
    if (
        job.get("id") != env["MIGRATION_JOB_ID"]
        or v.workload_fingerprint(job) != expected
        or configuration.get("triggerType") != "Manual"
        or configuration.get("replicaRetryLimit") != 0
        or configuration.get("manualTriggerConfig")
        != {"parallelism": 1, "replicaCompletionCount": 1}
        or len(containers) != 1
        or template.get("initContainers") not in (None, [])
        or template.get("volumes") not in (None, [])
    ):
        raise PlatformFailure("evaluation_reconciliation_existing_job_required")
    container = containers[0]
    from newsloom_platform.config import RuntimeConfig

    environment = {
        text_field(item, "name"): text_field(item, "value") for item in v.rows(container.get("env"))
    }
    config = RuntimeConfig.from_environment(environment)
    identity = config.identities["migrations"]
    if (
        json_object(job.get("identity")).get("type") != "UserAssigned"
        or {
            identifier.casefold()
            for identifier in json_object(
                json_object(job["identity"]).get("userAssignedIdentities")
            )
        }
        != {identity.id.casefold()}
        or environment.get("AZURE_CLIENT_ID") != str(identity.client_id)
        or container.get("command") not in (None, [])
        or container.get("args") != ["migrate"]
        or not re.fullmatch(r"[a-z0-9./:-]+@sha256:[a-f0-9]{64}", text_field(container, "image"))
    ):
        raise PlatformFailure("evaluation_reconciliation_job_identity_or_image")
    return {
        "container": container,
        "user_sha256": evaluation_record_probe.sha(config.postgres_admin_name),
    }


def execution_binding(
    env: dict[str, str],
    before: dict[str, object],
    failure: dict[str, object],
    transition: dict[str, str],
) -> dict[str, object]:
    return {
        **transition,
        "context_sha256": v.context(env),
        "baseline_sha256": v.digest(before),
        "failure_sha256": v.digest(failure),
        "program_sha256": hashlib.sha256(
            Path(evaluation_record_probe.__file__).read_bytes()
        ).hexdigest(),
        "job_id": env["MIGRATION_JOB_ID"],
    }


def validate_execution(
    evidence: v.Evidence,
    env: dict[str, str],
    before: dict[str, object],
    failure: dict[str, object],
    transition: dict[str, str],
    execution: dict[str, object],
) -> None:
    intent_path = str(evidence.directory / "reconciliation-execution-intent.json")
    intent = evidence.document(intent_path)
    expected = execution_binding(env, before, failure, transition)
    if (
        any(
            intent.get(key) != value or execution.get(key) != value
            for key, value in expected.items()
        )
        or execution.get("intent_sha256") != hashlib.sha256(evidence.read(intent_path)).hexdigest()
        or execution.get("outcome") != "success"
        or execution.get("job_unchanged") is not True
        or execution.get("execution_count") != 1
        or intent.get("replay_prohibited") is not True
        or not 0
        <= v.timestamp(execution.get("completed_utc")) - v.timestamp(intent.get("recorded_utc"))
        <= 600
    ):
        raise PlatformFailure("evaluation_reconciliation_execution_lineage")
    job = json_object(execution.get("job_before"))
    bound = job_boundary(job, env, before)
    if (
        execution.get("job_after_sha256") != v.workload_fingerprint(job)
        or intent.get("job_sha256") != v.workload_fingerprint(job)
        or json_object(execution.get("records")).get("identity_sha256") != bound["user_sha256"]
        or not v.timestamp(intent["recorded_utc"])
        <= v.timestamp(json_object(execution["records"]).get("verified_utc"))
        <= v.timestamp(execution["completed_utc"])
    ):
        raise PlatformFailure("evaluation_reconciliation_execution_identity")


def bounded_logs(arguments: list[str], timeout: int) -> str:
    # A real file avoids unbounded PIPE capture even if the CLI misbehaves.
    with tempfile.TemporaryFile() as output:
        process = subprocess.Popen(arguments, stdout=output, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + timeout
        try:
            while process.poll() is None:
                if (
                    time.monotonic() >= deadline
                    or output.tell() > evaluation_record_probe.MAX_BYTES
                ):
                    raise PlatformFailure("evaluation_reconciliation_log_limit")
                time.sleep(0.1)
            if process.returncode or output.tell() > evaluation_record_probe.MAX_BYTES:
                raise PlatformFailure("evaluation_reconciliation_log_failure")
            output.seek(0)
            return output.read(evaluation_record_probe.MAX_BYTES + 1).decode()
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()


def execute_records(
    evidence: v.Evidence,
    manifest: Manifest,
    env: dict[str, str],
    before: dict[str, object],
    failure: dict[str, object],
    transition: dict[str, str],
) -> None:
    intent_path = str(evidence.directory / "reconciliation-execution-intent.json")
    if evidence.path(intent_path).exists():
        raise PlatformFailure("evaluation_reconciliation_execution_already_consumed")
    reader = v.Reader(env, execution=True)
    job = reader.get(env["MIGRATION_JOB_ID"], control.API_VERSION)
    boundary = job_boundary(job, env, before)
    program = Path(evaluation_record_probe.__file__).read_text()
    cutoffs = [
        text_field(json_object(json_object(value["snapshot"])["stored_record"]), "verified_utc")
        for value in (before, failure)
    ]
    container = json_object(boundary["container"])
    request = {
        "containers": [
            {
                **{key: container[key] for key in ("name", "image", "resources", "env")},
                "command": ["/app/.venv/bin/python"],
                "args": ["-I", "-u", "-c", program, *cutoffs],
            }
        ]
    }
    binding = execution_binding(env, before, failure, transition)
    evidence.write(
        intent_path,
        {
            **binding,
            "job_sha256": v.workload_fingerprint(job),
            "request_sha256": v.digest(request),
            "recorded_utc": datetime.now(UTC).isoformat(),
            "replay_prohibited": True,
            "execution_limit_s": 600,
            "statement_limit_s": 60,
            "row_limit": 4096,
            "output_limit": 512 * 1024,
        },
    )
    # Reserve 30 seconds for an exact-execution stop inside the 600-second envelope.
    deadline = time.monotonic() + 570
    reader.deadline = deadline
    base = f"{v.ARM}{env['MIGRATION_JOB_ID']}"
    name: str | None = None
    state: object = None
    output: dict[str, object] = {
        **binding,
        "outcome": "failure",
        "category": "execution_outcome_unknown",
        "intent_sha256": hashlib.sha256(evidence.read(intent_path)).hexdigest(),
        "job_before": job,
        "execution_count": 1,
    }
    try:
        # This is the sole start; an ambiguous response consumes the authorization.
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json") as body:
            json.dump(request, body)
            body.flush()
            started = json_object(
                reader.cli(
                    [
                        "rest",
                        "--method",
                        "post",
                        "--url",
                        f"{base}/start?api-version={control.API_VERSION}",
                        "--body",
                        f"@{body.name}",
                    ]
                )
            )
        name = text_field(started, "name")
        if not re.fullmatch(r"[a-z0-9-]{1,80}", name):
            raise PlatformFailure("evaluation_reconciliation_invalid_execution")
        output["execution_name"] = name
        while time.monotonic() < deadline:
            status = reader.get(f"{env['MIGRATION_JOB_ID']}/executions/{name}", control.API_VERSION)
            state = json_object(status.get("properties")).get("status")
            if state == "Succeeded":
                break
            if state not in ("Processing", "Running", "Unknown"):
                raise PlatformFailure("evaluation_reconciliation_execution_failed")
            time.sleep(min(5, max(0, deadline - time.monotonic())))
        else:
            raise PlatformFailure("evaluation_reconciliation_execution_deadline")
        replicas = v.rows(
            reader.cli(
                [
                    "containerapp",
                    "job",
                    "replica",
                    "list",
                    "--name",
                    env["MIGRATION_JOB_ID"].rsplit("/", 1)[1],
                    "--resource-group",
                    env["AZURE_RESOURCE_GROUP"],
                    "--execution",
                    name,
                ]
            )
        )
        if len(replicas) != 1:
            raise PlatformFailure("evaluation_reconciliation_execution_replica_count")
        remaining = int(deadline - time.monotonic())
        if remaining < 1:
            raise PlatformFailure("evaluation_reconciliation_execution_deadline")
        logs = bounded_logs(
            [
                "az",
                "containerapp",
                "job",
                "logs",
                "show",
                "--name",
                env["MIGRATION_JOB_ID"].rsplit("/", 1)[1],
                "--resource-group",
                env["AZURE_RESOURCE_GROUP"],
                "--execution",
                name,
                "--replica",
                text_field(replicas[0], "name"),
                "--container",
                text_field(container, "name"),
                "--tail",
                "300",
                "--format",
                "text",
                "--only-show-errors",
            ],
            min(30, remaining),
        )
        output["records"] = parse_lines(logs)
        output["job_after_sha256"] = v.workload_fingerprint(
            reader.get(env["MIGRATION_JOB_ID"], control.API_VERSION)
        )
        output["job_unchanged"] = output["job_after_sha256"] == v.workload_fingerprint(job)
        output["outcome"] = "success"
        output.pop("category")
        output["completed_utc"] = datetime.now(UTC).isoformat()
        validate_execution(evidence, env, before, failure, transition, output)
    except (PlatformFailure, OSError, ValueError, subprocess.SubprocessError) as error:
        output["outcome"] = "failure"
        output["category"] = (
            str(error) if isinstance(error, PlatformFailure) else type(error).__name__
        )
        raise
    finally:
        output.setdefault("completed_utc", datetime.now(UTC).isoformat())
        evidence.write(manifest.output, output)
        if name is not None and state not in ("Succeeded", "Failed", "Stopped"):
            control.azure(
                [
                    "containerapp",
                    "job",
                    "stop",
                    "--ids",
                    env["MIGRATION_JOB_ID"],
                    "--job-execution-name",
                    name,
                    "--no-wait",
                ],
                "evaluation_reconciliation_exact_stop",
                timeout=30,
            )


def receipt(
    evidence: v.Evidence,
    path: str,
    env: dict[str, str],
    *,
    historical_source: str | None = None,
) -> dict[str, object]:
    value = evidence.document(path)
    if (
        value.get("source_sha256") != (historical_source or v.source(evidence.root))
        or value.get("context_sha256") != v.context(env)
        or value.get("layer") != "application"
        or value.get("mode") != "reconciliation"
        or value.get("outcome") != "success"
        or value.get("verification_scope") != v.verification_scope(env)
    ):
        raise PlatformFailure("evaluation_reconciliation_receipt_binding")
    inputs = json_object(value.get("inputs"))
    for entry in inputs.values():
        item = json_object(entry)
        if hashlib.sha256(evidence.read(text_field(item, "path"))).hexdigest() != item.get(
            "sha256"
        ):
            raise PlatformFailure("evaluation_reconciliation_changed_receipt_input")
    manifest = Manifest.model_validate(
        {
            "action": "verify",
            "output": path,
            **{key: text_field(json_object(item), "path") for key, item in inputs.items()},
        }
    )
    before, failure, transition = chain(evidence, manifest, env)
    if historical_source is not None:
        transition["source_sha256"] = v.fingerprint(historical_source)
    if any(value.get(key) != expected for key, expected in transition.items()):
        raise PlatformFailure("evaluation_reconciliation_receipt_transition")
    execution = evidence.document(text_field(manifest.model_dump(), "probe"))
    validate_execution(evidence, env, before, failure, transition, execution)
    stored = json_object(json_object(value.get("snapshot")).get("stored_record"))
    if stored != execution.get("records"):
        raise PlatformFailure("evaluation_reconciliation_receipt_records")
    counts = reconstructed(
        stored,
        json_object(json_object(before["snapshot"])["stored_record"]),
        json_object(json_object(failure["snapshot"])["stored_record"]),
        fresh=False,
    )
    if not 0 <= v.timestamp(value["verified_utc"]) - v.timestamp(
        stored["verified_utc"]
    ) <= 900 or counts != [
        value.get("original_count"),
        value.get("failed_readback_additions"),
        value.get("later_additions"),
    ]:
        raise PlatformFailure("evaluation_reconciliation_receipt_chronology")
    old, new = metadata(
        json_object(before["snapshot"]),
        json_object(value["snapshot"]),
        env,
        json_object(evidence.document(manifest.account_before).get("account")),
        json_object(value["account_preimage"]),
    )
    v.scoped_snapshot(json_object(value["snapshot"]), env)
    v.compare_authority(old, new, env, "application")
    return value


def captured_account(reader: v.Reader) -> dict[str, object]:
    if not isinstance(reader, AccountReader) or not reader.account:
        raise PlatformFailure("evaluation_reconciliation_account_preimage_required")
    return reader.account


def admit_snapshot(
    reconciliation: dict[str, object],
    current: dict[str, object],
    reader: v.Reader,
    env: dict[str, str],
) -> None:
    previous = json_object(reconciliation["snapshot"])
    v.scoped_snapshot(current, env)
    old, new = metadata(
        previous,
        current,
        env,
        json_object(reconciliation["account_preimage"]),
        captured_account(reader),
    )
    v.compare(old, new, env, "application")
