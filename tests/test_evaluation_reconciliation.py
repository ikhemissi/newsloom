import hashlib
import json
import os
import sys
import time
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile

import pytest
from newsloom_platform import cli, control
from newsloom_platform import evaluation_reconciliation as r
from newsloom_platform import evaluation_record_probe as probe
from newsloom_platform import evaluation_verification as v
from newsloom_platform.config import PlatformFailure, json_object
from pydantic import ValidationError
from test_evaluation_verification import (
    after_parent,
    after_project,
    native_binary,
    plan_for,
    preserved,
)
from test_evaluation_verification import (
    env as env,
)
from test_evaluation_verification import (
    evidence as evidence,
)


def record_evidence(count: int = 2) -> dict[str, object]:
    return {
        "schema": probe.SCHEMA,
        "outcome": "success",
        "verified_utc": datetime.now(UTC).isoformat(),
        "news_count": count,
        "rows": sorted(
            [[probe.sha(str(index)), probe.sha("content" + str(index))] for index in range(count)]
        ),
        "historical_membership": [],
        "reconstructions": [],
        "read_only": True,
        "identity_sha256": probe.sha("newsloom_mcp"),
        "statement_timeout_ms": 60000,
        "transaction_timeout_ms": 540000,
        "elapsed_ms": 1,
        "writes_performed": 0,
        "model_calls": 0,
    }


def raw_account(env: dict[str, str]) -> dict[str, object]:
    return {
        "id": env["MODEL_ACCOUNT_ID"],
        "name": env["MODEL_ACCOUNT_NAME"],
        "kind": "AIServices",
        "location": env["AZURE_LOCATION"],
        "sku": {"name": "S0"},
        "tags": {},
        "properties": {
            "disableLocalAuth": True,
            "endpoints": {"api": env["MODEL_ENDPOINT"]},
            "allowProjectManagement": False,
        },
    }


def metadata_pair(env: dict[str, str]) -> tuple[dict[str, object], ...]:
    raw_before = raw_account(env)
    raw_after = deepcopy(raw_before)
    json_object(raw_after["properties"])
    raw_after["properties"] = {
        **json_object(raw_after["properties"]),
        "armFeatures": [r.FEATURE],
        "allowProjectManagement": True,
    }
    before = preserved(env)
    before.pop("verification_scope")
    before["account"] = v.digest(v.account_invariant(raw_before))
    after = after_parent(before, env)
    after["account"] = v.digest(v.account_invariant(raw_after))
    role_id = (
        f"/subscriptions/{env['AZURE_SUBSCRIPTION_ID']}"
        f"/providers/Microsoft.Authorization/roleDefinitions/{uuid4()}"
    )
    role = {
        "id": role_id,
        "properties": {
            "type": "BuiltInRole",
            "roleName": "Reader",
            "assignableScopes": ["/"],
            "permissions": [
                {"actions": ["*/read"], "notActions": [], "dataActions": [], "notDataActions": []}
            ],
            "createdOn": "2020-01-01T00:00:00Z",
            "updatedOn": "2020-01-01T00:00:00Z",
        },
    }
    before["definitions"] = {role_id: role}
    after["definitions"] = deepcopy(before["definitions"])
    json_object(json_object(after["definitions"])[role_id])
    definitions = json_object(after["definitions"])
    new_role = json_object(definitions[role_id])
    new_role["properties"] = {
        **json_object(new_role["properties"]),
        "updatedOn": "2021-01-01T00:00:00Z",
    }
    definitions[role_id] = new_role
    after["definitions"] = definitions
    before["grants"] = after["grants"] = {
        "inherited": {
            "roleDefinitionId": role_id,
            "scope": f"/subscriptions/{env['AZURE_SUBSCRIPTION_ID']}",
        }
    }
    return before, after, raw_before, raw_after


def test_only_reviewed_metadata_is_admitted_without_mutating_receipts(env: dict[str, str]) -> None:
    before, after, raw_before, raw_after = metadata_pair(env)
    original = deepcopy((before, after, raw_before, raw_after))
    left, right = r.metadata(before, after, env, raw_before, raw_after)
    v.compare(left, right, env, "application")
    assert (before, after, raw_before, raw_after) == original


@pytest.mark.parametrize(
    "difference",
    [None, "default", "extra", "duplicate", "partial", "prior", "feature", "auth", "preimage"],
)
def test_exact_first_project_bookkeeping(env: dict[str, str], difference: str | None) -> None:
    _, parent, _, raw_before = metadata_pair(env)
    before = deepcopy(parent)
    raw_after = deepcopy(raw_before)
    properties = json_object(raw_after["properties"])
    name = v.project_id(env).rsplit("/", 1)[-1]
    properties.update(associatedProjects=[name], defaultProject=name)
    raw_after["properties"] = properties
    after = after_project(parent, env)
    if difference == "default":
        properties["defaultProject"] = "foreign"
    elif difference in ("extra", "duplicate"):
        properties["associatedProjects"] = [name, "foreign" if difference == "extra" else name]
    elif difference == "partial":
        properties.pop("defaultProject")
    elif difference == "prior":
        raw_before["properties"] = {**json_object(raw_before["properties"]), "defaultProject": name}
        before["account"] = v.digest(v.account_invariant(raw_before))
    elif difference == "feature":
        properties["armFeatures"] = [r.FEATURE, "Unreviewed"]
    elif difference == "auth":
        properties["disableLocalAuth"] = False
    after["account"] = (
        "0" * 64 if difference == "preimage" else v.digest(v.account_invariant(raw_after))
    )
    original = deepcopy((before, after, raw_before, raw_after))
    if difference is not None:
        with pytest.raises(PlatformFailure, match="evaluation_reconciliation_"):
            r.metadata(before, after, env, raw_before, raw_after, project_bookkeeping=True)
    else:
        with pytest.raises(PlatformFailure, match="unreviewed_feature"):
            r.metadata(before, after, env, raw_before, raw_after)
        old, new = r.metadata(before, after, env, raw_before, raw_after, project_bookkeeping=True)
        v.compare(old, new, env, "agent-evaluation")
    assert (before, after, raw_before, raw_after) == original


@pytest.fixture
def correction(
    evidence: v.Evidence, env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> tuple[v.Manifest, dict[str, object]]:
    allowed = (
        "services/platform/src/newsloom_platform/evaluation_verification.py",
        "services/platform/src/newsloom_platform/evaluation_reconciliation.py",
    )
    historical = {name: probe.sha("old:" + name) for name in allowed}
    historical["infra/main.tf"] = probe.sha("unchanged")
    current = {**historical, allowed[0]: probe.sha("corrected")}
    monkeypatch.setattr(v, "source_files", lambda root: current)
    archive_path = str(evidence.directory / "preimage.zip")
    with ZipFile(archive_path, "w") as archive:
        for name in allowed:
            archive.writestr(name, "old:" + name)
    Path(archive_path).chmod(0o600)
    paths = {
        key: str(evidence.directory / (key + ".json"))
        for key in ("preservation", "intent", "completion", "failure", "account_after")
    }
    evidence.write(
        paths["preservation"],
        {
            "source_sha256": v.digest(historical),
            "source_files": historical,
            "archive": archive_path,
            "archive_sha256": hashlib.sha256(Path(archive_path).read_bytes()).hexdigest(),
            "user_decision": "approve_exact_project_bookkeeping",
        },
    )
    binding: dict[str, object] = {
        "source_sha256": v.digest(current),
        "context_sha256": v.context(env),
        "verification_scope": v.verification_scope(env),
        "layer": "agent-evaluation",
    }
    baseline = str(evidence.directory / "baseline.json")
    review = str(evidence.directory / "review.json")
    plan = str(evidence.directory / "binary.tfplan")
    reconciliation = str(evidence.directory / "reconciliation.json")
    for path in (baseline, review, plan, reconciliation):
        evidence.write(path, {})
    now = datetime.now(UTC)
    evidence.write(
        paths["intent"],
        {
            "source_sha256": v.digest(historical),
            "layer": "agent-evaluation",
            "approved_plan_sha256": hashlib.sha256(evidence.read(plan)).hexdigest(),
            "recorded_utc": (now - timedelta(seconds=3)).isoformat(),
            "state_lock_enabled": True,
            "unknown_outcome_must_not_be_replayed": True,
        },
    )
    evidence.write(
        paths["completion"],
        {
            "source_sha256": v.digest(historical),
            "azd_exit_code": 0,
            "completed_utc": (now - timedelta(seconds=2)).isoformat(),
            "independent_readback_still_required": True,
        },
    )
    raw = raw_account(env)
    evidence.write(paths["account_after"], raw)
    evidence.write(
        paths["failure"],
        {
            **binding,
            "source_sha256": v.digest(historical),
            "mode": "readback",
            "outcome": "failure",
            "category": "evaluation_reconciliation_unreviewed_feature",
            "verified_utc": (now - timedelta(seconds=1)).isoformat(),
            "baseline_sha256": hashlib.sha256(evidence.read(baseline)).hexdigest(),
            "plan_sha256": hashlib.sha256(evidence.read(plan)).hexdigest(),
            "reconciliation_sha256": hashlib.sha256(evidence.read(reconciliation)).hexdigest(),
            "snapshot": {"account": v.digest(v.account_invariant(raw))},
        },
    )
    path = str(evidence.directory / "correction.json")
    evidence.write(path, paths)
    manifest = v.Manifest(
        mode="readback",
        layer="agent-evaluation",
        output="unused",
        baseline=baseline,
        review=review,
        plan=plan,
        reconciliation=reconciliation,
        stored_record="unused",
        correction=path,
    )
    return manifest, binding


@pytest.mark.parametrize(
    "difference",
    [None, "source", "inventory", "approval", "archive", "plan", "failure", "account", "time"],
)
def test_bookkeeping_correction_preserves_source_and_applied_lineage(
    evidence: v.Evidence,
    correction: tuple[v.Manifest, dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
    difference: str | None,
) -> None:
    manifest, binding = correction
    assert manifest.correction is not None
    paths = evidence.document(manifest.correction)
    if difference in ("source", "inventory"):
        current = v.source_files(evidence.root)
        current["infra/main.tf" if difference == "source" else "infra/new.tf"] = probe.sha("drift")
        monkeypatch.setattr(v, "source_files", lambda root: current)
    elif difference is not None:
        key = {
            "approval": "preservation",
            "archive": "preservation",
            "plan": "intent",
            "failure": "failure",
            "account": "account_after",
            "time": "completion",
        }[difference]
        path = str(paths[key])
        value = evidence.document(path)
        field, replacement = {
            "approval": ("user_decision", "unapproved"),
            "archive": ("archive_sha256", "0" * 64),
            "plan": ("approved_plan_sha256", "0" * 64),
            "failure": ("outcome", "success"),
            "account": ("name", "foreign"),
            "time": ("completed_utc", "2099-01-01T00:00:00Z"),
        }[difference]
        value[field] = replacement
        Path(path).write_text(json.dumps(value))
    if difference is None:
        result = v.readback_correction(evidence, manifest, binding)
        assert result["historical_source_sha256"] != binding["source_sha256"]
        assert set(json_object(result["inputs"])) == set(paths)
        assert evidence.document(str(paths["failure"]))["outcome"] == "failure"
    else:
        with pytest.raises(PlatformFailure, match="evaluation_verification_correction_"):
            v.readback_correction(evidence, manifest, binding)


def test_completed_apply_admission_does_not_refresh_historical_evidence() -> None:
    value: dict[str, object] = {
        "outcome": "success",
        "mode": "baseline",
        "verified_utc": "2020-01-01T00:00:00Z",
    }
    with pytest.raises(PlatformFailure, match="stale_evidence"):
        v.bound(value, {}, "baseline")
    admitted = v.timestamp("2020-01-01T00:30:00Z")
    v.bound(value, {}, "baseline", admitted_at=admitted)
    with pytest.raises(PlatformFailure, match="stale_evidence"):
        v.bound(value, {}, "baseline", admitted_at=admitted + 3601)


def test_global_definitions_are_excluded_but_rg_assignments_remain_checked(
    env: dict[str, str],
) -> None:
    before, after, raw_before, raw_after = metadata_pair(env)
    identifier = next(iter(json_object(before["definitions"])))
    before["grants"] = {"owned": {"roleDefinitionId": identifier, "scope": env["MODEL_ACCOUNT_ID"]}}
    after["grants"] = deepcopy(before["grants"])
    old, new = r.metadata(before, after, env, raw_before, raw_after)
    assert old["definitions"] == new["definitions"] == {}
    assert old["grants"] == new["grants"] == before["grants"]
    v.compare(old, new, env, "application")
    after["grants"] = {
        "owned": {
            "roleDefinitionId": identifier,
            "scope": env["MODEL_ACCOUNT_ID"],
            "condition": "unreviewed",
        }
    }
    with pytest.raises(PlatformFailure, match="unexpected_resource_or_authority"):
        old, new = r.metadata(before, after, env, raw_before, raw_after)
        v.compare(old, new, env, "application")


@pytest.mark.parametrize(
    "difference",
    [
        "feature",
        "endpoint",
        "auth",
        "preimage",
        "identity",
    ],
)
def test_metadata_cannot_conceal_authority_or_account_changes(
    env: dict[str, str],
    difference: str,
) -> None:
    before, after, raw_before, raw_after = metadata_pair(env)
    definitions = json_object(after["definitions"])
    role_id = next(iter(definitions))
    role = json_object(definitions[role_id])
    properties = json_object(role["properties"])
    if difference == "feature":
        raw_after["properties"] = {
            **json_object(raw_after["properties"]),
            "armFeatures": [r.FEATURE, "Unreviewed"],
        }
    elif difference in ("endpoint", "auth"):
        raw_after["properties"] = {
            **json_object(raw_after["properties"]),
            **({"endpoints": {}} if difference == "endpoint" else {"disableLocalAuth": False}),
        }
    elif difference == "preimage":
        after["account"] = "0" * 64
    elif difference == "identity":
        after["account_identity"] = {}
    elif difference == "nonglobal":
        properties["assignableScopes"] = [env["MODEL_ACCOUNT_ID"]]
        role["properties"] = properties
        definitions[role_id] = role
        after["definitions"] = definitions
    else:
        if difference == "custom":
            properties["type"] = "CustomRole"
        elif difference == "permission":
            properties["permissions"] = [{"actions": ["*"]}]
        elif difference == "scope":
            properties["assignableScopes"] = [env["MODEL_ACCOUNT_ID"]]
        else:
            properties["condition"] = "unreviewed"
        role["properties"] = properties
        definitions[role_id] = role
        after["definitions"] = definitions
    if difference in ("feature", "endpoint", "auth"):
        after["account"] = v.digest(v.account_invariant(raw_after))
    with pytest.raises(PlatformFailure):
        left, right = r.metadata(before, after, env, raw_before, raw_after)
        v.compare(left, right, env, "application")


def test_complete_fingerprints_admit_every_addition_and_preserve_every_original() -> None:
    before = record_evidence()
    after = record_evidence(5)
    assert len(r.appended(before, after)) == 3
    assert len(r.records(after)) == 5


@pytest.mark.parametrize(
    "difference",
    [
        "changed",
        "deleted",
        "duplicate",
        "partial",
        "order",
        "bool_count",
        "bool_time",
        "unknown",
        "not_read_only",
        "oversized",
        "stale",
        "extra_column",
        "bad_hash",
    ],
)
def test_full_record_evidence_fails_closed(difference: str) -> None:
    before, after = record_evidence(), record_evidence(3)
    rows = after["rows"]
    assert isinstance(rows, list)
    if difference == "changed":
        original = before["rows"]
        assert isinstance(original, list)
        changed_id = original[0][0]
        for row in rows:
            if row[0] == changed_id:
                row[1] = "f" * 64
    elif difference == "deleted":
        after["rows"] = rows[1:]
        after["news_count"] = 2
        # Ensure this removes an original, not only an addition.
        original = before["rows"]
        assert isinstance(original, list)
        after["rows"] = [row for row in rows if row[0] != original[0][0]]
    elif difference == "duplicate":
        after["rows"] = sorted([rows[0], rows[0], rows[1]])
    elif difference == "partial":
        after["rows"] = rows[:-1]
    elif difference == "order":
        after["rows"] = rows[::-1]
    elif difference == "bool_count":
        after["news_count"] = True
    elif difference == "bool_time":
        after["statement_timeout_ms"] = True
    elif difference == "unknown":
        after["unreviewed"] = 1
    elif difference == "not_read_only":
        after["read_only"] = False
    elif difference == "oversized":
        after["reconstructions"] = [{"padding": "a" * (512 * 1024)}]
    elif difference == "stale":
        after["verified_utc"] = (datetime.now(UTC) - timedelta(minutes=16)).isoformat()
    elif difference == "extra_column":
        rows[0].append("not_fingerprint")
    else:
        rows[0][1] = "not_fingerprint"
    with pytest.raises((PlatformFailure, ValidationError)):
        r.appended(before, after)


@pytest.mark.parametrize("count,accepted", [(4096, True), (4097, False)])
def test_row_and_wire_caps_are_independent(
    count: int,
    accepted: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    value = record_evidence(count)
    rows = value["rows"]
    assert isinstance(rows, list) and len(rows) == count
    with pytest.raises((PlatformFailure, ValueError)):
        r.records(value)
    monkeypatch.setattr(probe, "MAX_BYTES", 2 * 1024 * 1024)
    if accepted:
        assert len(r.records(value)) == 4096
    else:
        with pytest.raises(PlatformFailure, match="incomplete_record"):
            r.records(value)


def test_exact_evidence_byte_threshold_and_one_over(monkeypatch: pytest.MonkeyPatch) -> None:
    value = record_evidence()
    size = len(probe.encoded(value))
    monkeypatch.setattr(probe, "MAX_BYTES", size)
    assert len(r.records(value)) == 2
    monkeypatch.setattr(probe, "MAX_BYTES", size - 1)
    with pytest.raises(PlatformFailure, match="incomplete_record"):
        r.records(value)
    with pytest.raises(ValueError, match="evidence_limit"):
        probe.lines(value)


def test_chunk_protocol_is_complete_bounded_and_content_free() -> None:
    value = record_evidence(2000)
    output = "\n".join(probe.lines(value))
    assert len(output.encode()) <= 512 * 1024
    assert max(map(len, output.splitlines())) < 8192
    assert r.parse_lines(output) == value
    with pytest.raises(PlatformFailure, match="partial_probe"):
        r.parse_lines("\n".join(output.splitlines()[1:]))
    with pytest.raises(PlatformFailure, match="partial_probe"):
        r.parse_lines(output + "\n" + output.splitlines()[0])
    with pytest.raises(PlatformFailure, match="output_limit"):
        r.parse_lines("x" * (512 * 1024 + 1))


def historical_probe(before: dict[str, object], failed: dict[str, object]) -> dict[str, object]:
    value = record_evidence(3)
    value["historical_membership"] = [0, 0, 1]
    value["reconstructions"] = [
        {
            "cutoff_utc": item["verified_utc"],
            **{
                key: item[key]
                for key in (
                    "news_count",
                    "news_metadata_fingerprint",
                    "recent_id_sha256",
                    "recent_url_sha256",
                )
            },
        }
        for item in (before, failed)
    ]
    return value


@pytest.mark.parametrize(
    "key",
    [
        "news_count",
        "news_metadata_fingerprint",
        "recent_id_sha256",
        "recent_url_sha256",
        "verified_utc",
        "membership",
    ],
)
def test_historical_reconstruction_requires_every_exact_original_fingerprint(key: str) -> None:
    old = {
        "verified_utc": "2026-01-01T00:00:00+00:00",
        "news_count": 2,
        "news_metadata_fingerprint": "a" * 64,
        "recent_id_sha256": "b" * 64,
        "recent_url_sha256": "c" * 64,
    }
    failed = {**old, "news_count": 3, "verified_utc": "2026-01-01T01:00:00+00:00"}
    value = historical_probe(old, failed)
    assert r.reconstructed(value, old, failed) == [2, 1, 0]
    if key == "membership":
        value["historical_membership"] = [0, 1, 2]
    else:
        old[key] = "unmatched"
    with pytest.raises(PlatformFailure, match=r"historical_fingerprint|incomplete_record"):
        r.reconstructed(value, old, failed)


def test_mcp_v1_cannot_claim_migration_or_incomplete_evidence(evidence: v.Evidence) -> None:
    path = str(evidence.directory / "records.json")
    value = record_evidence()
    evidence.write(path, value)
    assert v.stored_record(evidence, path) == value
    other = str(evidence.directory / "wrong-identity.json")
    evidence.write(other, {**value, "identity_sha256": probe.sha("administrator")})
    with pytest.raises(PlatformFailure, match="independent_data"):
        v.stored_record(evidence, other)


def write_zip(evidence: v.Evidence, name: str, values: dict[str, bytes]) -> str:
    path = evidence.directory / name
    with (
        os.fdopen(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "wb") as stream,
        ZipFile(stream, "w") as archive,
    ):
        for key, content in values.items():
            archive.writestr(key, content)
    return str(path)


def migration_job(env: dict[str, str]) -> dict[str, object]:
    env["MIGRATION_JOB_ID"] = v.group_id(env) + "/providers/Microsoft.App/jobs/migrate-test"
    identities = {
        name: {
            "id": v.group_id(env)
            + "/providers/Microsoft.ManagedIdentity/userAssignedIdentities/"
            + name,
            "client_id": str(uuid4()),
            "principal_id": str(uuid4()),
        }
        for name in ("ingestion", "enrichment", "mcp", "migrations")
    }
    values = {
        "WORKLOAD_IDENTITIES": json.dumps(identities),
        "AZURE_CLIENT_ID": identities["migrations"]["client_id"],
        "POSTGRES_HOST": "retained.postgres.database.azure.com",
        "POSTGRES_DATABASE": "newsloom",
        "POSTGRES_ADMIN_NAME": "migration-admin",
        "MODEL_ENDPOINT": env["MODEL_ENDPOINT"],
        "MODEL_ACCOUNT_ID": env["MODEL_ACCOUNT_ID"],
        "ENRICHMENT_DEPLOYMENT": "chat",
        "EMBEDDINGS_DEPLOYMENT": "embeddings",
        "SCREENING_DEPLOYMENT": "screening",
        "AZURE_CONTAINER_REGISTRY_ENDPOINT": "test.azurecr.io",
        "APPLICATIONINSIGHTS_CONNECTION_STRING": "test",
    }
    return {
        "id": env["MIGRATION_JOB_ID"],
        "identity": {
            "type": "UserAssigned",
            "userAssignedIdentities": {identities["migrations"]["id"]: {}},
        },
        "properties": {
            "configuration": {
                "triggerType": "Manual",
                "replicaRetryLimit": 0,
                "replicaTimeout": 900,
                "manualTriggerConfig": {"parallelism": 1, "replicaCompletionCount": 1},
            },
            "template": {
                "containers": [
                    {
                        "name": "platform",
                        "image": "test.azurecr.io/platform@sha256:" + "a" * 64,
                        "command": None,
                        "args": ["migrate"],
                        "resources": {"cpu": 0.25, "memory": "0.5Gi"},
                        "env": [{"name": key, "value": value} for key, value in values.items()],
                    }
                ]
            },
        },
    }


@pytest.fixture
def retained_job(env: dict[str, str]) -> dict[str, object]:
    return migration_job(env)


@pytest.mark.parametrize("kind", ["casing", "foreign", "extra"])
def test_job_boundary_matches_arm_identity_case_insensitively(
    env: dict[str, str], retained_job: dict[str, object], kind: str
) -> None:
    identity = json_object(retained_job["identity"])
    identifier = next(iter(json_object(identity["userAssignedIdentities"])))
    identities: dict[str, object] = {identifier.lower(): {}}
    if kind == "foreign":
        identities = {identifier + "-foreign": {}}
    elif kind == "extra":
        identities[identifier + "-extra"] = {}
    identity["userAssignedIdentities"] = identities
    retained_job["identity"] = identity
    before: dict[str, object] = {
        "snapshot": {"workloads": {env["MIGRATION_JOB_ID"]: v.workload_fingerprint(retained_job)}}
    }
    if kind == "casing":
        assert r.job_boundary(retained_job, env, before)["container"]
    else:
        with pytest.raises(PlatformFailure, match="job_identity_or_image"):
            r.job_boundary(retained_job, env, before)


@pytest.fixture
def lineage(
    evidence: v.Evidence,
    env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    retained_job: dict[str, object],
) -> r.Manifest:
    root = evidence.root
    infra = root / "infra"
    infra.mkdir()
    (infra / "main.tf").write_text("unchanged infrastructure")
    (infra / ".terraform.lock.hcl").write_text(
        'provider "registry.terraform.io/hashicorp/azurerm" {\n  version = "5.10.0"\n}\n'
    )
    old_files = {
        "infra/main.tf": (infra / "main.tf").read_bytes(),
        "infra/.terraform.lock.hcl": (infra / ".terraform.lock.hcl").read_bytes(),
    }
    source_archive = write_zip(evidence, "source.zip", old_files)
    files = {path: hashlib.sha256(value).hexdigest() for path, value in old_files.items()}
    old_source = v.digest(files)
    monkeypatch.setattr(v, "source", lambda root: "f" * 64)
    original_run = control.run
    native = plan_for(env, "application")
    start = datetime.now(UTC) - timedelta(minutes=30)
    native["timestamp"] = start.isoformat()

    def run(arguments: list[str], category: str, **kwargs: object) -> str:
        if arguments[0] == "terraform":
            return json.dumps(native)
        if category == "evaluation_reconciliation_source":
            return "\0".join(old_files)
        return original_run(arguments, category, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(control, "run", run)
    before, after, raw_before, raw_after = metadata_pair(env)
    old_roles, new_roles = (json_object(value["definitions"]) for value in (before, after))
    template_id = next(iter(old_roles))
    for _ in range(9):
        identifier = template_id.rsplit("/", 1)[0] + "/" + str(uuid4())
        old_roles[identifier] = {**json_object(old_roles[template_id]), "id": identifier}
        new_roles[identifier] = {**json_object(new_roles[template_id]), "id": identifier}
    before["definitions"], after["definitions"] = old_roles, new_roles
    before["workloads"] = after["workloads"] = {
        env["MIGRATION_JOB_ID"]: v.workload_fingerprint(retained_job)
    }
    before["stored_record"] = {**json_object(before["stored_record"]), "news_count": 2}
    after["stored_record"] = {**json_object(after["stored_record"]), "news_count": 3}
    snapshots = [before, after]
    names: dict[str, str] = {}

    def put(key: str, value: object) -> str:
        path = str(evidence.directory / (key + ".json"))
        evidence.write(path, value)
        names[key] = path
        return path

    binding = {
        "context_sha256": v.context(env),
        "source_sha256": old_source,
        "layer": "application",
    }
    baseline = {
        **binding,
        "outcome": "success",
        "mode": "baseline",
        "verified_utc": (start - timedelta(seconds=1)).isoformat(),
        "snapshot": snapshots[0],
    }
    put("baseline", baseline)
    binary = native_binary(infra)
    plan = evidence.directory / "plan.bin"
    with os.fdopen(os.open(plan, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as stream:
        stream.write(binary)
    names["plan"] = str(plan)
    plan_hash = hashlib.sha256(binary).hexdigest()
    inventory = v.verify_plan(native, env, "application", reviewed_at=start.timestamp())
    review = {
        **binding,
        "outcome": "success",
        "mode": "plan",
        "verified_utc": start.isoformat(),
        "plan_sha256": plan_hash,
        "baseline_sha256": hashlib.sha256(evidence.read(names["baseline"])).hexdigest(),
        "plan_inventory": inventory,
    }
    put("review", review)
    put(
        "approval",
        {
            **binding,
            "recorded_utc": (start - timedelta(milliseconds=500)).isoformat(),
            "user_response": "approve_foundation_only",
            "project_and_two_operator_assignments_approved": True,
        },
    )
    put(
        "intent",
        {
            "source_sha256": old_source,
            "approved_plan_sha256": plan_hash,
            "recorded_utc": (start + timedelta(seconds=2)).isoformat(),
            "layer": "application",
            "state_lock_enabled": True,
            "unknown_outcome_must_not_be_replayed": True,
        },
    )
    put(
        "completion",
        {
            "azd_exit_code": 0,
            "layer": "application",
            "independent_readback_still_required": True,
            "completed_utc": (start + timedelta(seconds=3)).isoformat(),
        },
    )
    put(
        "failure",
        {
            **review,
            "outcome": "failure",
            "mode": "readback",
            "category": "evaluation_verification_preservation_drift",
            "verified_utc": (start + timedelta(seconds=4)).isoformat(),
            "snapshot": snapshots[1],
        },
    )
    evidence_archive = write_zip(
        evidence, "evidence.zip", {Path(path).name: evidence.read(path) for path in names.values()}
    )
    put(
        "preservation",
        {
            "source_archive_sha256": hashlib.sha256(evidence.read(source_archive)).hexdigest(),
            "evidence_archive_sha256": hashlib.sha256(evidence.read(evidence_archive)).hexdigest(),
            "historical_source_sha256": old_source,
            "source_files": files,
            "evidence_files": {
                Path(path).name: hashlib.sha256(evidence.read(path)).hexdigest()
                for path in names.values()
            },
            "preserved_utc": (start + timedelta(seconds=5)).isoformat(),
        },
    )
    put("account_before", {"account": raw_before})
    put("account_after", {"after_account": raw_after})
    monkeypatch.setattr(v, "retained_plan", lambda *args: None)
    return r.Manifest(
        action="execute-records",
        output=str(evidence.directory / "result.json"),
        source_archive=source_archive,
        evidence_archive=evidence_archive,
        **names,
    )


def test_historical_source_plan_and_failure_are_retained_and_bound(
    evidence: v.Evidence,
    env: dict[str, str],
    lineage: r.Manifest,
) -> None:
    before, failed, transition = r.chain(evidence, lineage, env)
    assert before["outcome"] == "success" and failed["outcome"] == "failure"
    assert transition["source_sha256"] == "f" * 64
    assert transition["historical_source_sha256"] != transition["source_sha256"]


@pytest.mark.parametrize(
    "key", ["baseline", "review", "intent", "completion", "failure", "approval"]
)
def test_rewritten_historical_evidence_never_passes(
    evidence: v.Evidence,
    env: dict[str, str],
    lineage: r.Manifest,
    key: str,
) -> None:
    path = Path(getattr(lineage, key))
    path.write_text("{}")
    with pytest.raises(PlatformFailure, match="original_evidence_changed"):
        r.chain(evidence, lineage, env)


def test_source_and_ownership_changes_never_pass(
    evidence: v.Evidence,
    env: dict[str, str],
    lineage: r.Manifest,
) -> None:
    (evidence.root / "infra/main.tf").write_text("unreviewed")
    with pytest.raises(PlatformFailure, match="unreviewed_source"):
        r.chain(evidence, lineage, env)
    Path(lineage.source_archive).chmod(0o644)
    with pytest.raises(PlatformFailure, match="private_file"):
        r.chain(evidence, lineage, env)


def test_historical_plan_time_does_not_weaken_normal_plan_freshness(env: dict[str, str]) -> None:
    plan = plan_for(env, "application")
    old = datetime.now(UTC) - timedelta(hours=4)
    plan["timestamp"] = old.isoformat()
    with pytest.raises(PlatformFailure, match="stale"):
        v.verify_plan(plan, env, "application")
    assert (
        v.verify_plan(plan, env, "application", reviewed_at=old.timestamp())["managed_resources"]
        == 32
    )


def test_log_reader_enforces_real_process_output_limit() -> None:
    with pytest.raises(PlatformFailure, match=r"log_failure|log_limit"):
        r.bounded_logs([sys.executable, "-c", "print('x' * 600000)"], 5)


def test_cli_dispatches_reconciliation_only_with_manifest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []
    monkeypatch.setattr(control, "environment", lambda: {"selected": "test"})
    monkeypatch.setattr(r, "verify", lambda *args: calls.append(args))
    monkeypatch.setattr(
        sys,
        "argv",
        ["newsloom-platform", "reconcile-agent-evaluation", "--manifest", "/private/manifest.json"],
    )
    cli.main()
    assert calls[0][0] == {"selected": "test"}
    assert calls[0][2] == "/private/manifest.json"


@pytest.mark.parametrize("outcome", ["success", "unknown", "failure", "deadline", "job_drift"])
def test_one_exact_read_only_execution_and_no_replay(
    evidence: v.Evidence,
    env: dict[str, str],
    lineage: r.Manifest,
    monkeypatch: pytest.MonkeyPatch,
    outcome: str,
    retained_job: dict[str, object],
) -> None:
    job = retained_job
    before, failure, transition = r.chain(evidence, lineage, env)
    calls: list[list[str]] = []
    started_requests: list[dict[str, object]] = []

    def get(reader: v.Reader, identifier: str, api: str = "") -> dict[str, object]:
        if "/executions/" in identifier:
            if outcome == "deadline":
                reader.deadline = time.monotonic() - 1
                raise PlatformFailure("evaluation_verification_metadata_limit")
            return {"properties": {"status": "Failed" if outcome == "failure" else "Succeeded"}}
        result = deepcopy(job)
        if outcome == "job_drift" and started_requests:
            result["identity"] = {}
        return result

    def azure(arguments: list[str], category: str, *, timeout: int) -> object:
        calls.append(arguments)
        assert 1 <= timeout <= 30
        if arguments[:3] == ["rest", "--method", "post"]:
            request = json.loads(Path(arguments[-1][1:]).read_text())
            started_requests.append(request)
            if outcome == "unknown":
                raise PlatformFailure("command_failed_start")
            return {"name": "migrate-test-verification"}
        if arguments[:4] == ["containerapp", "job", "replica", "list"]:
            return [{"name": "replica-one"}]
        if arguments[:3] == ["containerapp", "job", "stop"]:
            assert arguments[-3:] == [
                "--job-execution-name",
                "migrate-test-verification",
                "--no-wait",
            ]
            return {}
        raise AssertionError("unexpected mutation or read")

    def logs(arguments: list[str], timeout: int) -> str:
        value = historical_probe(
            json_object(json_object(before["snapshot"])["stored_record"]),
            json_object(json_object(failure["snapshot"])["stored_record"]),
        )
        value["identity_sha256"] = probe.sha("migration-admin")
        return "\n".join(probe.lines(value))

    monkeypatch.setattr(v.Reader, "get", get)
    monkeypatch.setattr(control, "azure", azure)
    monkeypatch.setattr(r, "bounded_logs", logs)
    if outcome == "success":
        r.execute_records(evidence, lineage, env, before, failure, transition)
    else:
        with pytest.raises(PlatformFailure):
            r.execute_records(evidence, lineage, env, before, failure, transition)
    result = evidence.document(lineage.output)
    assert result["outcome"] == ("success" if outcome == "success" else "failure")
    assert len(started_requests) == 1
    requested = v.rows(started_requests[0]["containers"])[0]
    original = v.rows(json_object(json_object(job["properties"])["template"])["containers"])[0]
    assert requested["image"] == original["image"] and requested["env"] == original["env"]
    assert requested["command"] == ["/app/.venv/bin/python"]
    arguments = requested["args"]
    assert isinstance(arguments, list)
    assert arguments[3] == Path(probe.__file__).read_text()
    assert arguments[4:] == [
        json_object(json_object(value["snapshot"])["stored_record"])["verified_utc"]
        for value in (before, failure)
    ]
    assert all(arguments[:3] != ["role", "assignment", "create"] for arguments in calls)
    with pytest.raises(PlatformFailure, match="already_consumed"):
        r.execute_records(evidence, lineage, env, before, failure, transition)
    assert len(started_requests) == 1


def test_reconciliation_receipt_and_admitted_snapshot_retain_original_failure(
    evidence: v.Evidence,
    env: dict[str, str],
    lineage: r.Manifest,
    monkeypatch: pytest.MonkeyPatch,
    retained_job: dict[str, object],
) -> None:
    job = retained_job
    before, failure, transition = r.chain(evidence, lineage, env)
    intent_path = str(evidence.directory / "reconciliation-execution-intent.json")
    binding = r.execution_binding(env, before, failure, transition)
    evidence.write(
        intent_path,
        {
            **binding,
            "job_sha256": v.workload_fingerprint(job),
            "recorded_utc": datetime.now(UTC).isoformat(),
            "replay_prohibited": True,
        },
    )
    data = historical_probe(
        json_object(json_object(before["snapshot"])["stored_record"]),
        json_object(json_object(failure["snapshot"])["stored_record"]),
    )
    data["identity_sha256"] = probe.sha("migration-admin")
    execution_path = str(evidence.directory / "execution.json")
    evidence.write(
        execution_path,
        {
            **binding,
            "records": data,
            "outcome": "success",
            "execution_count": 1,
            "intent_sha256": hashlib.sha256(evidence.read(intent_path)).hexdigest(),
            "job_unchanged": True,
            "job_before": job,
            "job_after_sha256": v.workload_fingerprint(job),
            "completed_utc": datetime.now(UTC).isoformat(),
        },
    )
    manifest_path = str(evidence.directory / "verify-manifest.json")
    manifest = lineage.model_copy(update={"action": "verify", "probe": execution_path})
    evidence.write(manifest_path, manifest.model_dump())
    current = v.scoped_snapshot(json_object(failure["snapshot"]), env, historical=True)
    raw = json_object(evidence.document(lineage.account_after)["after_account"])

    def snapshot(reader: r.AccountReader, environment: dict[str, str]) -> dict[str, object]:
        reader.account = raw
        return deepcopy(current)

    original_run = control.run

    def run(arguments: list[str], category: str, *, timeout: int = 300) -> str:
        if category == "project_root":
            return str(evidence.root)
        return original_run(arguments, category, timeout=timeout)

    monkeypatch.setattr(control, "run", run)
    monkeypatch.setattr(v, "operator", lambda *args: None)
    monkeypatch.setattr(v, "snapshot", snapshot)
    old_failure = evidence.read(lineage.failure)
    r.verify(env, "test", manifest_path)
    admitted = r.receipt(evidence, lineage.output, env)
    assert admitted["original_count"] == 2 and admitted["failed_readback_additions"] == 1
    assert evidence.read(lineage.failure) == old_failure
    assert evidence.document(lineage.failure)["outcome"] == "failure"
    with pytest.raises(PlatformFailure, match="output_already_exists"):
        r.verify(env, "test", manifest_path)
    # Historical proof remains usable; a new MCP read, not a new admin execution, admits growth.
    later = record_evidence(5)
    reader = r.AccountReader(env)
    reader.account = raw
    fresh_snapshot = {**current, "stored_record": later}
    r.admit_snapshot(admitted, fresh_snapshot, reader, env)


def set_nested(value: object, path: tuple[str | int, ...], replacement: object) -> None:
    for key in path[:-1]:
        if isinstance(key, int):
            assert isinstance(value, list)
            value = value[key]
        else:
            assert isinstance(value, dict)
            value = value[key]
    key = path[-1]
    if isinstance(key, int):
        assert isinstance(value, list)
        value[key] = replacement
    else:
        assert isinstance(value, dict)
        value[key] = replacement


def state_plan(env: dict[str, str]) -> dict[str, object]:
    plan = plan_for(env, "application")
    changes = v.rows(plan["resource_changes"])
    account = next(
        value for value in changes if value["address"] == "azurerm_cognitive_account.models"
    )
    change = json_object(account["change"])
    after = deepcopy(json_object(change["after"]))
    after["identity"] = [
        {
            "type": "SystemAssigned",
            "identity_ids": [],
            "principal_id": str(uuid4()),
            "tenant_id": env["AGENT_TENANT_ID"],
        }
    ]
    account["change"] = {
        "actions": ["no-op"],
        "before": deepcopy(after),
        "after": after,
        "after_unknown": {},
    }
    plan["resource_changes"] = changes
    for prefix in (("prior_state", "values"), ("planned_values",)):
        module = plan
        for key in prefix:
            module = json_object(module[key])
        for index, resource in enumerate(v.rows(json_object(module["root_module"])["resources"])):
            if resource["address"] == account["address"]:
                set_nested(
                    plan, (*prefix, "root_module", "resources", index, "values"), deepcopy(after)
                )
    identity = v.rows(after["identity"])[0]
    original = {**after, "identity": [{**identity, "identity_ids": None}]}
    plan["resource_drift"] = [
        {
            "address": account["address"],
            "change": {
                "actions": ["update"],
                "before": original,
                "after": deepcopy(after),
            },
        }
    ]
    plan["output_changes"] = {
        name: {
            "actions": ["create"],
            "before": None,
            "after": identity[field],
            "after_unknown": False,
        }
        for name, field in r.IDENTITY_OUTPUTS.items()
    }
    return plan


@pytest.mark.parametrize("difference", ["none", "write", "drift", "identity", "output", "unknown"])
def test_state_output_recovery_never_allows_resource_writes_or_broader_drift(
    env: dict[str, str],
    difference: str,
) -> None:
    plan = state_plan(env)
    if difference == "write":
        set_nested(plan, ("resource_changes", 0, "change", "actions"), ["update"])
    elif difference == "drift":
        plan["resource_drift"] = v.rows(plan["resource_drift"]) * 2
    elif difference == "identity":
        set_nested(
            plan, ("resource_drift", 0, "change", "after", "identity", 0, "type"), "UserAssigned"
        )
    elif difference == "output":
        set_nested(plan, ("output_changes", "foreign"), {"actions": ["create"]})
    elif difference == "unknown":
        set_nested(
            plan, ("output_changes", "MODEL_ACCOUNT_IDENTITY_PRINCIPAL_ID", "after_unknown"), True
        )
    if difference == "none":
        assert r.state_output_plan(plan, env)["mutations"] == 0
    else:
        with pytest.raises(PlatformFailure):
            r.state_output_plan(plan, env)


@pytest.mark.parametrize("difference", ["none", "resource", "lineage", "serial", "extra_output"])
def test_raw_state_transition_is_only_outputs_and_empty_identity_list(difference: str) -> None:
    before = {
        "serial": 1,
        "lineage": str(uuid4()),
        "outputs": {"retained": {"value": "unchanged"}},
        "resources": [
            {
                "type": "azurerm_cognitive_account",
                "name": "models",
                "instances": [
                    {"attributes": {"identity": [{"type": "SystemAssigned", "identity_ids": None}]}}
                ],
            }
        ],
    }
    after = deepcopy(before)
    after["serial"] = 2
    set_nested(
        after, ("resources", 0, "instances", 0, "attributes", "identity", 0, "identity_ids"), []
    )
    after["outputs"] = {
        **json_object(after["outputs"]),
        **{name: {"value": str(uuid4())} for name in r.IDENTITY_OUTPUTS},
    }
    if difference == "resource":
        set_nested(after, ("resources", 0, "instances", 0, "attributes", "foreign"), True)
    elif difference == "lineage":
        after["lineage"] = str(uuid4())
    elif difference == "serial":
        after["serial"] = 1
    elif difference == "extra_output":
        set_nested(after, ("outputs", "foreign"), {"value": True})
    if difference == "none":
        r.state_only_transition(before, after)
    else:
        with pytest.raises(PlatformFailure):
            r.state_only_transition(before, after)


def test_state_check_set_order_is_not_drift_but_payload_and_duplicates_are() -> None:
    first: dict[str, object] = {
        "check_results": [
            {
                "config_addr": "check.one",
                "objects": [
                    {"object_addr": "one.b", "status": "pass"},
                    {"object_addr": "one.a", "status": "pass"},
                ],
            },
            {"config_addr": "check.two", "objects": []},
        ]
    }
    second = deepcopy(first)
    set_nested(second, ("check_results",), list(reversed(v.rows(second["check_results"]))))
    assert r.canonical_state(first) == r.canonical_state(second)
    set_nested(second, ("check_results", 1, "objects", 0, "status"), "fail")
    assert r.canonical_state(first) != r.canonical_state(second)
    set_nested(second, ("check_results",), [v.rows(first["check_results"])[0]] * 2)
    with pytest.raises(PlatformFailure, match="duplicate_state_check"):
        r.canonical_state(second)
