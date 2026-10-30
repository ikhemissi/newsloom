"""Read-only, source-bound review of the two evaluation infrastructure boundaries."""

import base64
import hashlib
import io
import json
import os
import re
import stat
import time
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from zipfile import BadZipFile, ZipFile

from pydantic import BaseModel, ConfigDict, model_validator

from newsloom_platform import agent_evaluation, control, mcp_identity
from newsloom_platform.config import PlatformFailure, json_object, text_field
from newsloom_platform.events import event

ARM = "https://management.azure.com"
PROJECT_API = "2026-03-01"
ROLE_API = "2022-04-01"
MAX_BYTES = 32 * 1024 * 1024
APPLICATIONS = (
    "MCP_API_CLIENT_ID",
    "MCP_PUBLIC_CLIENT_ID",
    "AGENT_API_CLIENT_ID",
    "AGENT_PUBLIC_CLIENT_ID",
)
PERMISSIONS = {
    "chat": ["Microsoft.CognitiveServices/accounts/OpenAI/deployments/chat/completions/action"],
    "evaluations": [
        "Microsoft.CognitiveServices/accounts/AIServices/evaluations/delete",
        "Microsoft.CognitiveServices/accounts/AIServices/evaluations/read",
        "Microsoft.CognitiveServices/accounts/AIServices/evaluations/write",
        "Microsoft.CognitiveServices/accounts/OpenAI/evals/read",
        "Microsoft.CognitiveServices/accounts/OpenAI/evals/write",
    ],
}
CONTEXT = (
    "AZURE_SUBSCRIPTION_ID",
    "AZURE_ENV_NAME",
    "AZURE_RESOURCE_GROUP",
    "AZURE_LOCATION",
    "AGENT_TENANT_ID",
    "AGENT_EVALUATION_TENANT_ID",
    "AGENT_EVALUATION_OPERATOR_PRINCIPAL_ID",
    "MODEL_ACCOUNT_ID",
    "MODEL_ACCOUNT_NAME",
    "MODEL_ENDPOINT",
    "ENRICHMENT_DEPLOYMENT",
    "ENRICHMENT_MODEL",
    "ENRICHMENT_VERSION",
    "ENRICHMENT_FORMAT",
    "ENRICHMENT_SKU",
    "ENRICHMENT_CAPACITY",
    "POSTGRES_SERVER_NAME",
)


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)

    mode: Literal["baseline", "plan", "readback"]
    layer: Literal["application", "agent-evaluation"]
    output: str
    baseline: str | None = None
    plan: str | None = None
    review: str | None = None
    stored_record: str | None = None
    parent_readback: str | None = None
    reconciliation: str | None = None
    correction: str | None = None

    @model_validator(mode="after")
    def boundaries(self) -> Manifest:
        if self.correction is not None and (
            self.mode != "readback"
            or self.layer != "agent-evaluation"
            or self.reconciliation is None
        ):
            raise ValueError("Corrections require reconciled evaluation-layer readback.")
        expected = {
            "baseline": {"stored_record"},
            "plan": {"baseline", "plan"},
            "readback": {"baseline", "plan", "review", "stored_record"},
        }[self.mode]
        actual = {
            key
            for key in ("baseline", "plan", "review", "stored_record")
            if getattr(self, key) is not None
        }
        if actual != expected:
            raise ValueError("Evidence fields must match the selected verification mode.")
        if self.parent_readback is not None and (
            self.mode != "readback" or self.layer != "agent-evaluation"
        ):
            raise ValueError("Parent readback is only valid for evaluation-layer readback.")
        return self


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def rows(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list) or len(value) > 4096:
        raise PlatformFailure("evaluation_verification_invalid_inventory")
    return [json_object(row) for row in value]


def fingerprint(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value):
        raise PlatformFailure("evaluation_verification_invalid_fingerprint")
    return value


def timestamp(value: object) -> float:
    if not isinstance(value, str):
        raise PlatformFailure("evaluation_verification_missing_timestamp")
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() != UTC.utcoffset(None):
        raise PlatformFailure("evaluation_verification_timestamp_not_utc")
    return parsed.timestamp()


def fresh(value: object, maximum_age: int = 3600) -> None:
    if not 0 <= time.time() - timestamp(value) <= maximum_age:
        raise PlatformFailure("evaluation_verification_stale_evidence")


def source_files(root: Path) -> dict[str, str]:
    paths = [
        path
        for path in control.run(
            [
                "git",
                "-C",
                str(root),
                "ls-files",
                "--cached",
                "--others",
                "--exclude-standard",
                "-z",
            ],
            "evaluation_verification_source",
        ).split("\0")
        if path
        and (
            path.startswith(("infra/", "services/platform/", "tools/agent-evaluation/"))
            or path
            in (
                "azure.yaml",
                "pyproject.toml",
                "uv.lock",
                "config/agent-evaluation-pilot.json",
                "scripts/check.sh",
                "scripts/check-agent-evaluation.sh",
            )
        )
    ]
    if not paths or any(not (root / path).is_file() for path in paths):
        raise PlatformFailure("evaluation_verification_source_incomplete")
    return {path: hashlib.sha256((root / path).read_bytes()).hexdigest() for path in paths}


def source(root: Path) -> str:
    return digest(source_files(root))


class Evidence:
    def __init__(self, root: Path, environment: str):
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,31}", environment):
            raise PlatformFailure("evaluation_verification_invalid_environment")
        self.root = root.resolve()
        self.directory = self.root / ".azure" / environment / "evaluation-verification"

    def path(self, raw: str) -> Path:
        path = Path(raw)
        if not path.is_absolute():
            path = self.root / path
        if (
            path != path.resolve()
            or path.parent != self.directory
            or not self.directory.is_dir()
            or self.directory.stat().st_uid != os.getuid()
            or stat.S_IMODE(self.directory.stat().st_mode) != 0o700
        ):
            raise PlatformFailure("evaluation_verification_private_path_required")
        control.run(
            ["git", "-C", str(self.root), "check-ignore", str(path)],
            "evaluation_verification_ignored_path",
        )
        return path

    def read(self, raw: str) -> bytes:
        path = self.path(raw)
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as stream:
            metadata = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.getuid()
                or stat.S_IMODE(metadata.st_mode) != 0o600
                or not 0 < metadata.st_size <= MAX_BYTES
            ):
                raise PlatformFailure("evaluation_verification_private_file_required")
            value = stream.read(MAX_BYTES + 1)
        if len(value) > MAX_BYTES:
            raise PlatformFailure("evaluation_verification_evidence_too_large")
        return value

    def document(self, raw: str) -> dict[str, object]:
        def pairs(values: list[tuple[str, object]]) -> dict[str, object]:
            result: dict[str, object] = {}
            for key, value in values:
                if key in result:
                    raise PlatformFailure("evaluation_verification_duplicate_field")
                result[key] = value
            return result

        return json_object(json.loads(self.read(raw), object_pairs_hook=pairs))

    def write(self, raw: str, value: object) -> None:
        path = self.path(raw)
        content = json.dumps(value, sort_keys=True, indent=2, allow_nan=False).encode() + b"\n"
        if len(content) > MAX_BYTES:
            raise PlatformFailure("evaluation_verification_evidence_too_large")
        with os.fdopen(
            os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), "wb"
        ) as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())


def project_id(env: dict[str, str]) -> str:
    return f"{env['MODEL_ACCOUNT_ID']}/projects/eval-newsloom-{env['AZURE_ENV_NAME']}"


def group_id(env: dict[str, str]) -> str:
    return (
        f"/subscriptions/{env['AZURE_SUBSCRIPTION_ID']}"
        f"/resourceGroups/{env['AZURE_RESOURCE_GROUP']}"
    )


def in_group(identifier: str, env: dict[str, str]) -> bool:
    group = group_id(env).casefold()
    return identifier.casefold() == group or identifier.casefold().startswith(group + "/")


def verification_scope(env: dict[str, str]) -> dict[str, object]:
    return {
        "schema": "newsloom-rg-verification-v1",
        "resource_group": group_id(env),
        "database": env["POSTGRES_DATABASE"],
        "database_server": env["POSTGRES_SERVER_NAME"],
        "app_registrations": sorted(mcp_identity.identifier(env[key]) for key in APPLICATIONS),
        "excluded": [
            "inherited_grants",
            "cross_resource_group_assignments",
            "global_builtin_definitions",
            "subscription_quota_and_catalogs",
            "unrelated_directory_objects",
            "other_databases",
        ],
    }


def evaluation_roles(env: dict[str, str]) -> set[str]:
    raw = env.get("AGENT_EVALUATION_GRANTS_BASE64")
    if not raw:
        return set()
    grants = json_object(json.loads(base64.b64decode(raw, validate=True)))
    if set(grants) != set(PERMISSIONS):
        raise PlatformFailure("evaluation_verification_grant_output_inventory")
    return {text_field(json_object(value), "role_definition_id") for value in grants.values()}


def scoped_snapshot(
    value: dict[str, object], env: dict[str, str], *, historical: bool = False
) -> dict[str, object]:
    scope = verification_scope(env)
    if value.get("verification_scope") != scope and (
        not historical or value.get("verification_scope") is not None
    ):
        raise PlatformFailure("evaluation_verification_scope_evidence_required")
    result = deepcopy(value)
    result["verification_scope"] = scope
    assignments = json_object(value.get("grants"))
    permitted = evaluation_roles(env)
    if value.get("verification_scope") is not None and (
        any(
            not in_group(text_field(json_object(item), "scope"), env)
            for item in assignments.values()
        )
        or json_object(value.get("definitions")).keys() - permitted
    ):
        raise PlatformFailure("evaluation_verification_outside_scope_evidence")
    result["grants"] = {
        identifier: assignment
        for identifier, assignment in assignments.items()
        if in_group(text_field(json_object(assignment), "scope"), env)
    }
    result["definitions"] = {
        identifier: definition
        for identifier, definition in json_object(value.get("definitions")).items()
        if identifier in permitted
    }
    return result


def context(env: dict[str, str]) -> str:
    if any(not env.get(key) for key in CONTEXT):
        raise PlatformFailure("evaluation_verification_context_required")
    if env["AGENT_EVALUATION_TENANT_ID"] != env["AGENT_TENANT_ID"]:
        raise PlatformFailure("evaluation_verification_tenant_mismatch")
    for key in (
        "AZURE_SUBSCRIPTION_ID",
        "AGENT_TENANT_ID",
        "AGENT_EVALUATION_OPERATOR_PRINCIPAL_ID",
    ):
        if mcp_identity.identifier(env[key]) != env[key]:
            raise PlatformFailure("evaluation_verification_context_mismatch")
    suffix = hashlib.sha256(
        f"{env['AZURE_SUBSCRIPTION_ID']}/{env['AZURE_ENV_NAME']}".encode()
    ).hexdigest()[:8]
    account = f"ai-newsloom-{env['AZURE_ENV_NAME']}-{suffix}"
    if (
        env["MODEL_ACCOUNT_NAME"] != account
        or env["MODEL_ACCOUNT_ID"]
        != f"{group_id(env)}/providers/Microsoft.CognitiveServices/accounts/{account}"
        or env["MODEL_ENDPOINT"] != f"https://{account}.services.ai.azure.com/"
    ):
        raise PlatformFailure("evaluation_verification_foreign_account")
    return digest({key: env[key] for key in CONTEXT})


def permission_row(label: str) -> dict[str, object]:
    return {
        "actions": [],
        "not_actions": [],
        "data_actions": PERMISSIONS[label],
        "not_data_actions": [],
    }


def normalized_permissions(value: object) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for row in rows(value):
        if set(row) != {"actions", "not_actions", "data_actions", "not_data_actions"}:
            raise PlatformFailure("evaluation_verification_invalid_permissions")
        normalized: dict[str, object] = {}
        for key, operations in row.items():
            if key == "not_data_actions" and operations is None:
                operations = []
            if (
                not isinstance(operations, list)
                or any(not isinstance(item, str) or not item for item in operations)
                or len(operations) != len(set(operations))
            ):
                raise PlatformFailure("evaluation_verification_invalid_permissions")
            normalized[key] = sorted(operations)
        result.append(normalized)
    return result


def unknown_paths(value: object, prefix: tuple[str, ...] = ()) -> set[tuple[str, ...]]:
    if value is True:
        return {prefix}
    if isinstance(value, dict):
        return set().union(
            *(unknown_paths(item, (*prefix, str(key))) for key, item in value.items())
        )
    if isinstance(value, list):
        return set().union(
            *(unknown_paths(item, (*prefix, str(index))) for index, item in enumerate(value))
        )
    if value is not False and value is not None:
        raise PlatformFailure("evaluation_verification_invalid_unknowns")
    return set()


def indexed(value: object, key: str = "address") -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for row in rows(value):
        name = text_field(row, key)
        if name in result:
            raise PlatformFailure("evaluation_verification_duplicate_resource")
        result[name] = row
    return result


def application_addresses() -> set[str]:
    fixed = {
        "azurerm_resource_group.application",
        "azurerm_container_registry.application",
        "azurerm_log_analytics_workspace.application",
        "azurerm_application_insights.application",
        "azurerm_container_app_environment.application",
        "azurerm_monitor_diagnostic_setting.containers",
        "azurerm_postgresql_flexible_server.application",
        "azurerm_postgresql_flexible_server_database.application",
        "azurerm_postgresql_flexible_server_firewall_rule.azure_services",
        "azurerm_postgresql_flexible_server_configuration.extensions",
        "azurerm_postgresql_flexible_server_active_directory_administrator.migrations",
        "azurerm_cognitive_account.models",
    }
    return fixed | {
        f'{resource}["{label}"]'
        for resource, labels in (
            (
                "azurerm_user_assigned_identity.workload",
                ("ingestion", "enrichment", "mcp", "migrations"),
            ),
            (
                "azurerm_role_assignment.registry_pull",
                ("ingestion", "enrichment", "mcp", "migrations"),
            ),
            ("azurerm_role_assignment.telemetry", ("ingestion", "enrichment", "mcp")),
            ("azurerm_cognitive_deployment.model", ("screening", "enrichment", "embeddings")),
            ("azurerm_role_definition.inference", ("ingestion", "enrichment", "mcp")),
            ("azurerm_role_assignment.inference", ("ingestion", "enrichment", "mcp")),
        )
        for label in labels
    }


def verify_plan(
    plan: dict[str, object],
    env: dict[str, str],
    layer: str,
    *,
    reviewed_at: float | None = None,
) -> dict[str, object]:
    if (
        plan.get("format_version") != "1.2"
        or plan.get("terraform_version") != "1.15.8"
        or plan.get("complete") is not True
        or plan.get("errored") is not False
        or plan.get("deferred_changes")
    ):
        raise PlatformFailure("evaluation_verification_incomplete_native_plan")
    if (
        not 0
        <= (time.time() if reviewed_at is None else reviewed_at) - timestamp(plan.get("timestamp"))
        <= 3600
    ):
        raise PlatformFailure("evaluation_verification_stale_evidence")
    if any(check.get("status") in ("fail", "error") for check in rows(plan.get("checks", []))):
        raise PlatformFailure("evaluation_verification_native_check_failed")
    for drift in rows(plan.get("resource_drift", [])):
        if json_object(drift.get("change")).get("actions") != ["no-op"]:
            raise PlatformFailure("evaluation_verification_unreviewed_state_drift")
    configuration = json_object(plan.get("configuration"))
    provider = json_object(json_object(configuration.get("provider_config")).get("azurerm"))
    if provider.get("version_constraint") != "5.10.0":
        raise PlatformFailure("evaluation_verification_provider_mismatch")
    configured = json_object(configuration.get("root_module"))
    if configured.get("module_calls"):
        raise PlatformFailure("evaluation_verification_unexpected_module")
    variables = json_object(plan.get("variables"))
    expected_variables: dict[str, object] = {
        "subscription_id": env["AZURE_SUBSCRIPTION_ID"],
        "environment_name": env["AZURE_ENV_NAME"],
        "resource_group_name": env["AZURE_RESOURCE_GROUP"],
        "location": env["AZURE_LOCATION"],
    }
    if layer == "agent-evaluation":
        native_enabled = json_object(variables.get("enabled")).get("value")
        if native_enabled is not True and native_enabled != "true":
            raise PlatformFailure("evaluation_verification_plan_context_mismatch")
        expected_variables.update(
            enabled=native_enabled,
            tenant_id=env["AGENT_TENANT_ID"],
            operator_principal_id=env["AGENT_EVALUATION_OPERATOR_PRINCIPAL_ID"],
            model_account_id=env["MODEL_ACCOUNT_ID"],
            model_endpoint=env["MODEL_ENDPOINT"],
        )
    if any(
        json_object(variables.get(key)).get("value") != value
        for key, value in expected_variables.items()
    ):
        raise PlatformFailure("evaluation_verification_plan_context_mismatch")
    resources = indexed(plan.get("resource_changes"))
    managed = {key: value for key, value in resources.items() if value.get("mode") == "managed"}
    expected = (
        application_addresses()
        if layer == "application"
        else {"azurerm_cognitive_account_project.evaluation[0]"}
        | {
            f'{kind}.operator["{label}"]'
            for kind in ("azurerm_role_definition", "azurerm_role_assignment")
            for label in PERMISSIONS
        }
    )
    if set(managed) != expected:
        raise PlatformFailure("evaluation_verification_plan_resource_boundary")
    prior_values = json_object(json_object(plan.get("prior_state", {})).get("values", {}))
    prior_module = json_object(prior_values.get("root_module", {}))
    planned_module = json_object(json_object(plan.get("planned_values")).get("root_module"))
    if prior_module.get("child_modules") or planned_module.get("child_modules"):
        raise PlatformFailure("evaluation_verification_unexpected_module")
    prior = {
        key: row
        for key, row in indexed(prior_module.get("resources", [])).items()
        if row.get("mode") == "managed"
    }
    planned = {
        key: row
        for key, row in indexed(planned_module.get("resources")).items()
        if row.get("mode") == "managed"
    }
    if set(planned) != expected or not set(prior) <= expected:
        raise PlatformFailure("evaluation_verification_state_inventory_mismatch")
    if layer == "application" and set(prior) != expected:
        raise PlatformFailure("evaluation_verification_retained_state_required")
    for address, resource in resources.items():
        if resource.get("provider_name") != "registry.terraform.io/hashicorp/azurerm":
            raise PlatformFailure("evaluation_verification_foreign_provider")
        change = json_object(resource.get("change"))
        if (
            resource.get("previous_address")
            or change.get("importing")
            or change.get("replace_paths")
        ):
            raise PlatformFailure("evaluation_verification_move_import_or_replace")
        if resource.get("mode") == "data":
            expected_data = "data.azurerm_client_config.current" + (
                "[0]" if layer == "agent-evaluation" else ""
            )
            after = json_object(change.get("after"))
            if (
                address != expected_data
                or change.get("actions") not in (["read"], ["no-op"])
                or after.get("subscription_id") != env["AZURE_SUBSCRIPTION_ID"]
                or after.get("tenant_id") != env["AGENT_TENANT_ID"]
                or after.get("object_id") != env["AGENT_EVALUATION_OPERATOR_PRINCIPAL_ID"]
                or unknown_paths(change.get("after_unknown"))
            ):
                raise PlatformFailure("evaluation_verification_provider_context_mismatch")
            continue
        if address not in managed:
            raise PlatformFailure("evaluation_verification_invalid_resource_mode")
        before = change.get("before")
        after = json_object(change.get("after"))
        if (
            (address in prior and before != prior[address].get("values"))
            or (address not in prior and before is not None)
            or after != planned[address].get("values")
        ):
            raise PlatformFailure("evaluation_verification_plan_state_disagreement")
        unknown = unknown_paths(change.get("after_unknown"))
        actions = change.get("actions")
        if layer == "application":
            if address != "azurerm_cognitive_account.models":
                if actions != ["no-op"] or before != after or unknown:
                    raise PlatformFailure("evaluation_verification_unrelated_application_change")
            else:
                verify_account_plan(json_object(before), after, unknown, actions, env)
        else:
            if actions not in (["create"], ["no-op"]) or (
                actions == ["no-op"] and (before != after or unknown)
            ):
                raise PlatformFailure("evaluation_verification_unapproved_evaluation_action")
            verify_evaluation_resource(address, after, unknown, configured, env)
    return {
        "managed_resources": len(managed),
        "mutations": sum(
            json_object(value["change"])["actions"] != ["no-op"] for value in managed.values()
        ),
        "inventory": {
            label: {
                "principal_id": env["AGENT_EVALUATION_OPERATOR_PRINCIPAL_ID"],
                "principal_type": "User",
                "scope": env["MODEL_ACCOUNT_ID"] if label == "chat" else project_id(env),
                **permission_row(label),
            }
            for label in PERMISSIONS
        }
        if layer == "agent-evaluation"
        else {},
    }


def verify_account_plan(
    before: dict[str, object],
    after: dict[str, object],
    unknown: set[tuple[str, ...]],
    actions: object,
    env: dict[str, str],
) -> None:
    allowed = {"identity", "project_management_enabled"}
    identities = rows(after.get("identity"))
    if (
        actions not in (["update"], ["no-op"])
        or {key: value for key, value in before.items() if key not in allowed}
        != {key: value for key, value in after.items() if key not in allowed}
        or after.get("id") != env["MODEL_ACCOUNT_ID"]
        or after.get("name") != env["MODEL_ACCOUNT_NAME"]
        or after.get("kind") != "AIServices"
        or after.get("sku_name") != "S0"
        or after.get("local_auth_enabled") is not False
        or after.get("project_management_enabled") is not True
        or len(identities) != 1
        or identities[0].get("type") != "SystemAssigned"
        or identities[0].get("identity_ids")
        or not unknown <= {("identity", "0", "principal_id"), ("identity", "0", "tenant_id")}
    ):
        raise PlatformFailure("evaluation_verification_account_change_boundary")
    old = rows(before.get("identity") or [])
    if old and old[0].get("type") == "SystemAssigned" and identities != old:
        raise PlatformFailure("evaluation_verification_retained_identity_changed")
    if actions == ["no-op"] and (before != after or unknown):
        raise PlatformFailure("evaluation_verification_invalid_noop")


def references(configured: dict[str, object], address: str, field: str, allowed: set[str]) -> None:
    resource = indexed(configured.get("resources")).get(address)
    if resource is None:
        raise PlatformFailure("evaluation_verification_missing_configuration")
    expression = json_object(json_object(resource.get("expressions")).get(field))
    actual = expression.get("references")
    if (
        not isinstance(actual, list)
        or not actual
        or any(not isinstance(item, str) for item in actual)
        or not set(actual) <= allowed
    ):
        raise PlatformFailure("evaluation_verification_unbound_computed_reference")
    if not any(isinstance(item, str) and item.startswith("azurerm_") for item in actual):
        raise PlatformFailure("evaluation_verification_unbound_computed_reference")


def verify_evaluation_resource(
    address: str,
    after: dict[str, object],
    unknown: set[tuple[str, ...]],
    configured: dict[str, object],
    env: dict[str, str],
) -> None:
    if address == "azurerm_cognitive_account_project.evaluation[0]":
        identities = rows(after.get("identity"))
        if (
            after.get("name") != project_id(env).rsplit("/", 1)[1]
            or after.get("cognitive_account_id") != env["MODEL_ACCOUNT_ID"]
            or after.get("location") != env["AZURE_LOCATION"]
            or len(identities) != 1
            or identities[0].get("type") != "SystemAssigned"
            or identities[0].get("identity_ids")
            or after.get("id") not in (None, project_id(env))
            or not unknown
            <= {
                ("id",),
                ("default",),
                ("endpoints",),
                ("identity", "0", "principal_id"),
                ("identity", "0", "tenant_id"),
            }
        ):
            raise PlatformFailure("evaluation_verification_project_boundary")
        return
    label = "chat" if address.endswith('["chat"]') else "evaluations"
    if address.startswith("azurerm_role_definition."):
        if (
            after.get("name") != f"newsloom-{env['AZURE_ENV_NAME']}-agent-evaluation-{label}"
            or after.get("scope") != group_id(env)
            or after.get("assignable_scopes") != [group_id(env)]
            or normalized_permissions(after.get("permissions")) != [permission_row(label)]
            or not unknown <= {("id",), ("role_definition_id",), ("role_definition_resource_id",)}
        ):
            raise PlatformFailure("evaluation_verification_role_boundary")
        return
    scope = env["MODEL_ACCOUNT_ID"] if label == "chat" else project_id(env)
    if (
        after.get("principal_id") != env["AGENT_EVALUATION_OPERATOR_PRINCIPAL_ID"]
        or after.get("principal_type") != "User"
        or after.get("condition") not in ("", None)
        or after.get("condition_version") not in ("", None)
        or after.get("delegated_managed_identity_resource_id") not in ("", None)
        or after.get("role_definition_name")
        not in ("", None, f"newsloom-{env['AZURE_ENV_NAME']}-agent-evaluation-{label}")
        or after.get("skip_service_principal_aad_check") not in (False, None)
        or not unknown
        <= {
            ("id",),
            ("name",),
            ("role_definition_id",),
            ("scope",),
            ("condition_version",),
            ("role_definition_name",),
            ("skip_service_principal_aad_check",),
        }
    ):
        raise PlatformFailure("evaluation_verification_assignment_boundary")
    if after.get("scope") != scope:
        if label != "evaluations" or ("scope",) not in unknown or after.get("scope") is not None:
            raise PlatformFailure("evaluation_verification_assignment_scope")
        references(
            configured,
            "azurerm_role_assignment.operator",
            "scope",
            {
                "each.key",
                "var.model_account_id",
                "azurerm_cognitive_account_project.evaluation",
                "azurerm_cognitive_account_project.evaluation[0]",
                "azurerm_cognitive_account_project.evaluation[0].id",
            },
        )
    references(
        configured,
        "azurerm_role_assignment.operator",
        "role_definition_id",
        {"each.key", "azurerm_role_definition.operator"},
    )
    definition = after.get("role_definition_id")
    if definition is not None and not isinstance(definition, str):
        raise PlatformFailure("evaluation_verification_invalid_role_reference")


class Reader:
    def __init__(self, env: dict[str, str], *, execution: bool = False) -> None:
        self.env = env
        self.execution = execution
        self.applications = {env[key] for key in APPLICATIONS if env.get(key)}
        self.deadline = time.monotonic() + 600
        self.calls = 0

    def guard(self, arguments: list[str]) -> None:
        allowed = arguments == ["account", "show"] or arguments == agent_evaluation.OPERATOR_TOKEN
        if arguments[:3] == ["rest", "--method", "get"] and len(arguments) == 5:
            parsed = urlsplit(arguments[4])
            allowed = (
                arguments[3] == "--url"
                and parsed.scheme == "https"
                and parsed.netloc == "management.azure.com"
                and not parsed.fragment
                and not any(part in (".", "..") for part in parsed.path.split("/"))
                and "%" not in parsed.path
                and in_group(parsed.path, self.env)
            )
            if "/providers/microsoft.authorization/roledefinitions" in parsed.path.casefold():
                allowed = allowed and parsed.path.rsplit("/", 1)[1].casefold() in {
                    identifier.rsplit("/", 1)[1].casefold()
                    for identifier in evaluation_roles(self.env)
                }
            if "/databases" in parsed.path.casefold():
                database = (
                    group_id(self.env)
                    + "/providers/Microsoft.DBforPostgreSQL/flexibleServers/"
                    + self.env["POSTGRES_SERVER_NAME"]
                    + "/databases/"
                    + self.env["POSTGRES_DATABASE"]
                )
                allowed = allowed and parsed.path.casefold() == database.casefold()
        elif arguments[:2] == ["ad", "app"]:
            permitted = (
                (["ad", "app", "show", "--id"], {self.env[key] for key in APPLICATIONS}),
                (["ad", "app", "federated-credential", "list", "--id"], self.applications),
                (
                    ["ad", "app", "permission", "list-grants", "--id"],
                    {self.env[key] for key in APPLICATIONS},
                ),
            )
            allowed = any(
                arguments[:-1] == prefix and arguments[-1] in identifiers
                for prefix, identifiers in permitted
            )
        elif arguments[:3] == ["rest", "--method", "post"]:
            allowed = (
                self.execution
                and len(arguments) == 7
                and arguments[3:6]
                == [
                    "--url",
                    f"{ARM}{self.env.get('MIGRATION_JOB_ID')}/start?api-version={control.API_VERSION}",
                    "--body",
                ]
                and arguments[6].startswith("@")
                and in_group(self.env.get("MIGRATION_JOB_ID", ""), self.env)
            )
        elif arguments[:4] == ["containerapp", "job", "replica", "list"]:
            allowed = (
                len(arguments) == 10
                and arguments[4:9]
                == [
                    "--name",
                    self.env.get("MIGRATION_JOB_ID", "").rsplit("/", 1)[-1],
                    "--resource-group",
                    self.env["AZURE_RESOURCE_GROUP"],
                    "--execution",
                ]
                and re.fullmatch(r"[a-z0-9-]{1,80}", arguments[9]) is not None
                and in_group(self.env.get("MIGRATION_JOB_ID", ""), self.env)
            )
        elif arguments[:3] == ["postgres", "flexible-server", "show"]:
            expected = (
                group_id(self.env)
                + "/providers/Microsoft.DBforPostgreSQL/flexibleServers/"
                + self.env["POSTGRES_SERVER_NAME"]
            )
            allowed = arguments == ["postgres", "flexible-server", "show", "--ids", expected]
        elif arguments[:2] == ["postgres", "flexible-server"] and len(arguments) == 8:
            allowed = arguments[2] in ("microsoft-entra-admin", "firewall-rule") and arguments[
                3:
            ] == [
                "list",
                "--resource-group",
                self.env["AZURE_RESOURCE_GROUP"],
                "--server-name",
                self.env["POSTGRES_SERVER_NAME"],
            ]
        if not allowed:
            raise PlatformFailure("evaluation_verification_outside_scope")

    def cli(self, arguments: list[str]) -> object:
        self.guard(arguments)
        remaining = self.deadline - time.monotonic()
        if self.calls >= 100 or remaining < 1:
            raise PlatformFailure("evaluation_verification_metadata_limit")
        self.calls += 1
        value = control.azure(
            arguments, "evaluation_verification_metadata", timeout=min(30, int(remaining))
        )
        if len(json.dumps(value).encode()) > MAX_BYTES:
            raise PlatformFailure("evaluation_verification_metadata_too_large")
        return value

    def get(self, identifier: str, api: str = agent_evaluation.ARM_API) -> dict[str, object]:
        if not re.fullmatch(r"/subscriptions/[A-Za-z0-9_()./|-]+", identifier):
            raise PlatformFailure("evaluation_verification_invalid_resource_id")
        return json_object(
            self.cli(["rest", "--method", "get", "--url", f"{ARM}{identifier}?api-version={api}"])
        )

    def listing(self, identifier: str, api: str) -> list[dict[str, object]]:
        if not re.fullmatch(r"/subscriptions/[A-Za-z0-9_()./-]+", identifier):
            raise PlatformFailure("evaluation_verification_invalid_resource_id")
        url = f"{ARM}{identifier}?api-version={api}"
        prefix = urlsplit(url).path
        found: list[dict[str, object]] = []
        seen: set[str] = set()
        for _ in range(10):
            if url in seen:
                raise PlatformFailure("evaluation_verification_pagination_cycle")
            seen.add(url)
            page = json_object(self.cli(["rest", "--method", "get", "--url", url]))
            found.extend(rows(page.get("value")))
            if len(found) > 4096:
                raise PlatformFailure("evaluation_verification_inventory_limit")
            next_url = page.get("nextLink")
            if next_url in (None, ""):
                return found
            if not isinstance(next_url, str):
                raise PlatformFailure("evaluation_verification_invalid_next_link")
            parsed = urlsplit(next_url)
            if (
                parsed.scheme != "https"
                or parsed.netloc != "management.azure.com"
                or parsed.path != prefix
                or parsed.fragment
                or f"api-version={api}" not in parsed.query.split("&")
            ):
                raise PlatformFailure("evaluation_verification_foreign_next_link")
            url = next_url
        raise PlatformFailure("evaluation_verification_page_limit")


def operator(reader: Reader, env: dict[str, str]) -> None:
    account = json_object(reader.cli(["account", "show"]))
    if (
        account.get("id") != env["AZURE_SUBSCRIPTION_ID"]
        or account.get("tenantId") != env["AGENT_TENANT_ID"]
        or account.get("state") != "Enabled"
        or json_object(account.get("user")).get("type") != "user"
        or agent_evaluation.operator_from_token(
            reader.cli(agent_evaluation.OPERATOR_TOKEN), env["AGENT_TENANT_ID"]
        )
        != env["AGENT_EVALUATION_OPERATOR_PRINCIPAL_ID"]
    ):
        raise PlatformFailure("evaluation_verification_operator_mismatch")


def system_identity(value: object, env: dict[str, str], *, required: bool) -> dict[str, object]:
    identity = json_object(value or {})
    if identity.get("type") in (None, "None") and not required:
        if identity.get("principalId") or identity.get("userAssignedIdentities"):
            raise PlatformFailure("evaluation_verification_account_identity_mismatch")
        return {}
    principal = mcp_identity.identifier(identity.get("principalId"))
    if (
        identity.get("type") != "SystemAssigned"
        or identity.get("tenantId") != env["AGENT_TENANT_ID"]
        or principal == env["AGENT_EVALUATION_OPERATOR_PRINCIPAL_ID"]
        or identity.get("userAssignedIdentities")
    ):
        raise PlatformFailure("evaluation_verification_account_identity_mismatch")
    return {"type": "SystemAssigned", "principalId": principal, "tenantId": identity["tenantId"]}


def stored_record(evidence: Evidence, path: str) -> dict[str, object]:
    value = evidence.document(path)
    if value.get("schema") == "news-metadata-v1":
        from newsloom_platform import evaluation_reconciliation
        from newsloom_platform.evaluation_record_probe import sha

        evaluation_reconciliation.records(value)
        if (
            value.get("identity_sha256") != sha("newsloom_mcp")
            or value.get("historical_membership") != []
            or value.get("reconstructions") != []
        ):
            raise PlatformFailure("evaluation_verification_independent_data_evidence_required")
        return value
    if set(value) != {
        "verified_utc",
        "outcome",
        "probe",
        "mcp_read_identity_verified",
        "news_count",
        "news_metadata_fingerprint",
        "recent_id_sha256",
        "recent_url_sha256",
        "writes_performed",
        "model_calls",
    } or (
        value.get("outcome") != "success"
        or value.get("probe") != "independent_stored_record"
        or value.get("mcp_read_identity_verified") is not True
        or type(value.get("news_count")) is not int
        or int(str(value["news_count"])) < 1
        or type(value.get("writes_performed")) is not int
        or value["writes_performed"] != 0
        or type(value.get("model_calls")) is not int
        or value["model_calls"] != 0
    ):
        raise PlatformFailure("evaluation_verification_independent_data_evidence_required")
    fresh(value["verified_utc"], 900)
    for key in ("news_metadata_fingerprint", "recent_id_sha256", "recent_url_sha256"):
        fingerprint(value[key])
    return value


def directory_snapshot(reader: Reader, env: dict[str, str]) -> str:
    inventory: dict[str, object] = {}
    for key in APPLICATIONS:
        identifier = mcp_identity.identifier(env[key])
        application = json_object(reader.cli(["ad", "app", "show", "--id", identifier]))
        if application.get("appId") != identifier:
            raise PlatformFailure("evaluation_verification_directory_evidence_missing")
        object_id = mcp_identity.identifier(application.get("id"))
        reader.applications.add(object_id)
        inventory[key] = application
        inventory[key + "_federation"] = rows(
            reader.cli(
                [
                    "ad",
                    "app",
                    "federated-credential",
                    "list",
                    "--id",
                    object_id,
                ]
            )
        )
        inventory[key + "_consent"] = rows(
            reader.cli(
                [
                    "ad",
                    "app",
                    "permission",
                    "list-grants",
                    "--id",
                    identifier,
                ]
            )
        )
    return digest(
        {
            key: sorted(value, key=digest) if isinstance(value, list) else value
            for key, value in inventory.items()
        }
    )


def database_boundary(reader: Reader, identifier: str, env: dict[str, str]) -> str:
    if identifier != (
        f"{group_id(env)}/providers/Microsoft.DBforPostgreSQL"
        f"/flexibleServers/{env['POSTGRES_SERVER_NAME']}"
    ):
        raise PlatformFailure("evaluation_verification_foreign_database")
    server = json_object(reader.cli(["postgres", "flexible-server", "show", "--ids", identifier]))
    auth = json_object(server.get("authConfig"))
    if (
        server.get("id") != identifier
        or server.get("state") != "Ready"
        or auth.get("passwordAuth") != "Disabled"
        or auth.get("activeDirectoryAuth") != "Enabled"
        or auth.get("tenantId") != env["AGENT_TENANT_ID"]
    ):
        raise PlatformFailure("evaluation_verification_database_auth_boundary")
    inventory: dict[str, object] = {
        key: server.get(key)
        for key in (
            "id",
            "name",
            "type",
            "location",
            "sku",
            "identity",
            "authConfig",
            "network",
            "storage",
            "backup",
            "highAvailability",
            "replicationRole",
            "version",
            "fullyQualifiedDomainName",
            "availabilityZone",
            "maintenanceWindow",
            "dataEncryption",
        )
    }
    for kind in ("microsoft-entra-admin", "firewall-rule"):
        inventory[kind] = sorted(
            rows(
                reader.cli(
                    [
                        "postgres",
                        "flexible-server",
                        kind,
                        "list",
                        "--resource-group",
                        env["AZURE_RESOURCE_GROUP"],
                        "--server-name",
                        env["POSTGRES_SERVER_NAME"],
                    ]
                )
            ),
            key=digest,
        )
    return digest(inventory)


def snapshot(reader: Reader, env: dict[str, str]) -> dict[str, object]:
    account = reader.get(env["MODEL_ACCOUNT_ID"])
    properties = json_object(account.get("properties"))
    if (
        account.get("id") != env["MODEL_ACCOUNT_ID"]
        or account.get("name") != env["MODEL_ACCOUNT_NAME"]
        or account.get("location") != env["AZURE_LOCATION"]
        or account.get("kind") != "AIServices"
        or json_object(account.get("sku")).get("name") != "S0"
        or properties.get("provisioningState") != "Succeeded"
        or properties.get("disableLocalAuth") is not True
        or properties.get("customSubDomainName") != env["MODEL_ACCOUNT_NAME"]
        or type(properties.get("allowProjectManagement")) is not bool
        or env["MODEL_ENDPOINT"].rstrip("/")
        not in {
            str(value).rstrip("/") for value in json_object(properties.get("endpoints")).values()
        }
    ):
        raise PlatformFailure("evaluation_verification_account_readback")
    identity = system_identity(account.get("identity"), env, required=False)
    invariant = account_invariant(account)
    models = indexed(
        reader.listing(env["MODEL_ACCOUNT_ID"] + "/deployments", agent_evaluation.ARM_API), "id"
    )
    if len(models) != 3:
        raise PlatformFailure("evaluation_verification_model_inventory")
    chat_id = f"{env['MODEL_ACCOUNT_ID']}/deployments/{env['ENRICHMENT_DEPLOYMENT']}"
    chat = models.get(chat_id)
    if chat is None:
        raise PlatformFailure("evaluation_verification_chat_missing")
    for model in models.values():
        if json_object(model.get("properties")).get(
            "provisioningState"
        ) != "Succeeded" or not text_field(model, "id").startswith(
            env["MODEL_ACCOUNT_ID"] + "/deployments/"
        ):
            raise PlatformFailure("evaluation_verification_model_inventory")
    chat_properties = json_object(chat.get("properties"))
    if (
        json_object(chat_properties.get("model"))
        != {
            "format": env["ENRICHMENT_FORMAT"],
            "name": env["ENRICHMENT_MODEL"],
            "version": env["ENRICHMENT_VERSION"],
        }
        or json_object(chat_properties.get("capabilities")).get("chatCompletion") != "true"
        or chat_properties.get("versionUpgradeOption") != "NoAutoUpgrade"
        or json_object(chat.get("sku")).get("name") != env["ENRICHMENT_SKU"]
        or type(json_object(chat.get("sku")).get("capacity")) is not int
        or json_object(chat.get("sku"))["capacity"] != int(env["ENRICHMENT_CAPACITY"])
    ):
        raise PlatformFailure("evaluation_verification_chat_drift")
    return runtime_snapshot(reader, env, account, identity, invariant, models)


def account_invariant(account: dict[str, object]) -> dict[str, object]:
    return {
        "id": account["id"],
        "name": account["name"],
        "kind": account["kind"],
        "location": account["location"],
        "sku": account["sku"],
        "tags": account.get("tags"),
        "properties": {
            key: value
            for key, value in json_object(account.get("properties")).items()
            if key not in ("allowProjectManagement", "provisioningState")
        },
    }


def workload_fingerprint(native: dict[str, object]) -> str:
    settings = json_object(native.get("properties"))
    return digest(
        {
            "identity": native.get("identity"),
            **{
                key: settings.get(key)
                for key in (
                    "environmentId",
                    "workloadProfileName",
                    "configuration",
                    "template",
                    "latestRevisionName",
                    "latestReadyRevisionName",
                )
            },
        }
    )


def runtime_snapshot(
    reader: Reader,
    env: dict[str, str],
    account: dict[str, object],
    identity: dict[str, object],
    invariant: dict[str, object],
    models: dict[str, dict[str, object]],
) -> dict[str, object]:
    resources = indexed(reader.listing(group_id(env) + "/resources", "2021-04-01"), "id")
    resource_hashes: dict[str, str] = {}
    workloads: dict[str, str] = {}
    principals: set[str] = {env["AGENT_EVALUATION_OPERATOR_PRINCIPAL_ID"]}
    expected_workload_identities = {
        (
            group_id(env)
            + "/providers/Microsoft.ManagedIdentity/userAssignedIdentities/"
            + f"id-newsloom-{env['AZURE_ENV_NAME']}-{workload}"
        ).casefold()
        for workload in ("ingestion", "enrichment", "mcp", "migrations", "agent")
    }
    workload_principals: set[str] = set()
    histories: dict[str, object] = {}
    data_boundaries: dict[str, str] = {}
    for identifier, resource in resources.items():
        if not identifier.casefold().startswith(group_id(env).casefold() + "/providers/"):
            raise PlatformFailure("evaluation_verification_foreign_resource")
        resource_hashes[identifier] = digest(
            {
                key: value
                for key, value in resource.items()
                if key in ("id", "name", "type", "location", "tags")
            }
        )
        kind = text_field(resource, "type").casefold()
        if kind == "microsoft.managedidentity/userassignedidentities":
            native = reader.get(identifier, "2023-01-31")
            principal = mcp_identity.identifier(
                json_object(native.get("properties")).get("principalId")
            )
            principals.add(principal)
            if identifier.casefold() in expected_workload_identities:
                workload_principals.add(principal)
            workloads[identifier] = digest(native.get("properties"))
        elif kind in ("microsoft.app/containerapps", "microsoft.app/jobs"):
            native = reader.get(identifier, control.API_VERSION)
            settings = json_object(native.get("properties"))
            if settings.get("provisioningState") != "Succeeded":
                raise PlatformFailure("evaluation_verification_workload_not_ready")
            if kind == "microsoft.app/containerapps" and (
                not settings.get("latestRevisionName")
                or settings.get("latestRevisionName") != settings.get("latestReadyRevisionName")
            ):
                raise PlatformFailure("evaluation_verification_workload_not_ready")
            for required in ("environmentId", "configuration", "template"):
                if required not in settings:
                    raise PlatformFailure("evaluation_verification_workload_evidence_missing")
            workloads[identifier] = workload_fingerprint(native)
            if kind == "microsoft.app/jobs":
                executions = reader.listing(identifier + "/executions", control.API_VERSION)
                histories[identifier] = {
                    text_field(item, "id"): {
                        key: json_object(item.get("properties")).get(key)
                        for key in ("status", "startTime", "endTime")
                    }
                    for item in executions
                }
        elif kind == "microsoft.dbforpostgresql/flexibleservers":
            data_boundaries[identifier] = database_boundary(reader, identifier, env)
    if (
        len(workload_principals) != 5
        or len(data_boundaries) != 1
        or sum(
            text_field(item, "type").casefold()
            in ("microsoft.app/containerapps", "microsoft.app/jobs")
            for item in resources.values()
        )
        != 6
    ):
        raise PlatformFailure("evaluation_verification_runtime_inventory")
    projects = indexed(reader.listing(env["MODEL_ACCOUNT_ID"] + "/projects", PROJECT_API), "id")
    project: dict[str, object] = {}
    if project_id(env) in projects:
        project = reader.get(project_id(env), PROJECT_API)
        project_identity = system_identity(project.get("identity"), env, required=True)
        if project_identity == identity:
            raise PlatformFailure("evaluation_verification_reused_managed_identity")
        principals.add(text_field(project_identity, "principalId"))
    if identity:
        principals.add(text_field(identity, "principalId"))
    assignments = reader.listing(
        group_id(env) + "/providers/Microsoft.Authorization/roleAssignments", ROLE_API
    )
    grants: dict[str, object] = {}
    definitions: dict[str, object] = {}
    for assignment in assignments:
        properties = json_object(assignment.get("properties"))
        if not in_group(text_field(properties, "scope"), env):
            continue
        identifier = text_field(assignment, "id")
        definition_id = text_field(properties, "roleDefinitionId")
        if identifier in grants:
            raise PlatformFailure("evaluation_verification_duplicate_assignment")
        grants[identifier] = {
            "id": identifier,
            **{
                key: properties.get(key)
                for key in (
                    "principalId",
                    "principalType",
                    "roleDefinitionId",
                    "scope",
                    "condition",
                    "conditionVersion",
                    "delegatedManagedIdentityResourceId",
                )
            },
        }
        if definition_id in evaluation_roles(env) and definition_id not in definitions:
            definition = reader.get(
                group_id(env)
                + "/providers/Microsoft.Authorization/roleDefinitions/"
                + definition_id.rsplit("/", 1)[1],
                ROLE_API,
            )
            role = json_object(definition.get("properties"))
            if role.get("type") != "CustomRole" or role.get("assignableScopes") != [group_id(env)]:
                raise PlatformFailure("evaluation_verification_foreign_role_definition")
            definitions[definition_id] = definition
    return {
        "verification_scope": verification_scope(env),
        "account": digest(invariant),
        "account_identity": identity,
        "project_management": json_object(account["properties"])["allowProjectManagement"],
        "models": models,
        "resources": resource_hashes,
        "workloads": workloads,
        "histories": histories,
        "data_boundaries": data_boundaries,
        "projects": {key: digest(value) for key, value in projects.items()},
        "project": project,
        "grants": grants,
        "definitions": definitions,
        "production_principals": sorted(
            principals
            - {
                env["AGENT_EVALUATION_OPERATOR_PRINCIPAL_ID"],
                *([text_field(identity, "principalId")] if identity else []),
                *(
                    [text_field(json_object(project.get("identity")), "principalId")]
                    if project
                    else []
                ),
            }
        ),
        "directory": directory_snapshot(reader, env),
    }


def retained_plan(
    plan: dict[str, object], baseline: dict[str, object], env: dict[str, str], layer: str
) -> None:
    if layer == "agent-evaluation":
        if project_id(env) in json_object(baseline.get("projects")):
            raise PlatformFailure("evaluation_verification_fresh_project_baseline_required")
        resources = indexed(plan.get("resource_changes"))
        for label in PERMISSIONS:
            definition = json_object(
                json_object(resources[f'azurerm_role_definition.operator["{label}"]']["change"])[
                    "after"
                ]
            )
            assignment_change = json_object(
                resources[f'azurerm_role_assignment.operator["{label}"]']["change"]
            )
            assignment = json_object(assignment_change["after"])
            role_id = definition.get("role_definition_resource_id")
            if assignment.get("role_definition_id") != role_id or (
                role_id is None
                and ("role_definition_id",)
                not in unknown_paths(assignment_change.get("after_unknown"))
            ):
                raise PlatformFailure("evaluation_verification_foreign_role_reference")
        return
    resources = indexed(plan.get("resource_changes"))
    account = json_object(
        json_object(resources["azurerm_cognitive_account.models"]["change"])["before"]
    )
    identity = rows(account.get("identity") or [])
    native_identity = json_object(baseline.get("account_identity"))
    if (
        account.get("project_management_enabled") != baseline.get("project_management")
        or bool(identity) != bool(native_identity)
        or (
            identity
            and (
                identity[0].get("principal_id") != native_identity.get("principalId")
                or identity[0].get("tenant_id") != native_identity.get("tenantId")
                or identity[0].get("type") != native_identity.get("type")
            )
        )
    ):
        raise PlatformFailure("evaluation_verification_stale_account_plan")
    models = json_object(baseline.get("models"))
    found: set[str] = set()
    for address, resource in resources.items():
        if not address.startswith("azurerm_cognitive_deployment.model["):
            continue
        before = json_object(json_object(resource["change"])["before"])
        identifier = text_field(before, "id")
        model = json_object(models.get(identifier))
        settings = json_object(model.get("properties"))
        configured_model = rows(before.get("model"))
        configured_sku = rows(before.get("sku"))
        if (
            before.get("name") != model.get("name")
            or before.get("cognitive_account_id") != env["MODEL_ACCOUNT_ID"]
            or before.get("version_upgrade_option") != settings.get("versionUpgradeOption")
            or len(configured_model) != 1
            or len(configured_sku) != 1
            or any(
                configured_model[0].get(key) != json_object(settings.get("model")).get(key)
                for key in ("name", "version", "format")
            )
            or any(
                configured_sku[0].get(key) != json_object(model.get("sku")).get(key)
                for key in ("name", "capacity")
            )
        ):
            raise PlatformFailure("evaluation_verification_stale_model_plan")
        found.add(identifier)
    if found != set(models):
        raise PlatformFailure("evaluation_verification_stale_model_inventory")


def compare_authority(
    before: dict[str, object], after: dict[str, object], env: dict[str, str], layer: str
) -> None:
    before, after = scoped_snapshot(before, env), scoped_snapshot(after, env)
    for key in (
        "account",
        "models",
        "workloads",
        "directory",
        "production_principals",
        "data_boundaries",
    ):
        if before.get(key) != after.get(key):
            raise PlatformFailure("evaluation_verification_preservation_drift")
    identity = json_object(after.get("account_identity"))
    system_identity(identity, env, required=True)
    if (
        after.get("project_management") is not True
        or (before.get("account_identity") and before["account_identity"] != identity)
        or (
            env.get("MODEL_PROJECT_MANAGEMENT_ENABLED") != "true"
            or env.get("MODEL_ACCOUNT_IDENTITY_PRINCIPAL_ID") != identity["principalId"]
            or env.get("MODEL_ACCOUNT_IDENTITY_TENANT_ID") != identity["tenantId"]
        )
    ):
        raise PlatformFailure("evaluation_verification_parent_prerequisite_drift")
    resources = json_object(after.get("resources"))
    projects = json_object(after.get("projects"))
    grants = json_object(after.get("grants"))
    definitions = json_object(after.get("definitions"))
    if layer == "agent-evaluation":
        if (
            before.get("account_identity") != identity
            or before.get("project_management") is not True
        ):
            raise PlatformFailure("evaluation_verification_parent_was_not_ready")
        project = json_object(after.get("project"))
        project_identity = system_identity(project.get("identity"), env, required=True)
        settings = json_object(project.get("properties"))
        endpoint = (
            env["MODEL_ENDPOINT"].rstrip("/") + "/api/projects/" + project_id(env).rsplit("/", 1)[1]
        )
        native_endpoints = json_object(settings.get("endpoints"))
        if (
            project.get("id") != project_id(env)
            or project.get("name")
            not in (
                project_id(env).rsplit("/", 1)[1],
                env["MODEL_ACCOUNT_NAME"] + "/" + project_id(env).rsplit("/", 1)[1],
            )
            or project.get("location") != env["AZURE_LOCATION"]
            or settings.get("provisioningState") != "Succeeded"
            or endpoint not in {str(value).rstrip("/") for value in native_endpoints.values()}
            or env.get("AGENT_EVALUATION_PROJECT_ID") != project_id(env)
            or env.get("AGENT_EVALUATION_PROJECT_ENDPOINT", "").rstrip("/") != endpoint
            or env.get("AGENT_EVALUATION_PROJECT_PRINCIPAL_ID") != project_identity["principalId"]
            or json.loads(
                base64.b64decode(env["AGENT_EVALUATION_PROJECT_ENDPOINTS_BASE64"], validate=True)
            )
            != native_endpoints
        ):
            raise PlatformFailure("evaluation_verification_project_readback_mismatch")
        if project_id(env) in json_object(before.get("projects")):
            raise PlatformFailure("evaluation_verification_fresh_project_baseline_required")
        resources.pop(project_id(env), None)
        if projects.pop(project_id(env), None) is None:
            raise PlatformFailure("evaluation_verification_project_inventory_missing")
        output_grants = json_object(
            json.loads(base64.b64decode(env["AGENT_EVALUATION_GRANTS_BASE64"], validate=True))
        )
        if set(output_grants) != set(PERMISSIONS):
            raise PlatformFailure("evaluation_verification_grant_output_inventory")
        for label in PERMISSIONS:
            expected_scope = env["MODEL_ACCOUNT_ID"] if label == "chat" else project_id(env)
            matches = [
                (identifier, json_object(value))
                for identifier, value in grants.items()
                if json_object(value).get("principalId")
                == env["AGENT_EVALUATION_OPERATOR_PRINCIPAL_ID"]
                and json_object(value).get("scope") == expected_scope
                and identifier not in json_object(before.get("grants"))
            ]
            if len(matches) != 1:
                raise PlatformFailure("evaluation_verification_exact_assignment_missing")
            identifier, assignment = matches[0]
            definition_id = text_field(assignment, "roleDefinitionId")
            definition = json_object(definitions.get(definition_id))
            role = json_object(definition.get("properties"))
            expected = permission_row(label)
            output = json_object(output_grants[label]).copy()
            output.update(
                normalized_permissions(
                    [{key: value for key, value in output.items() if key in expected}]
                )[0]
            )
            actual_permissions = [
                {
                    "actions": row.get("actions"),
                    "not_actions": row.get("notActions"),
                    "data_actions": row.get("dataActions"),
                    "not_data_actions": row.get("notDataActions"),
                }
                for row in rows(role.get("permissions"))
            ]
            if (
                assignment.get("principalType") != "User"
                or assignment.get("condition") not in (None, "")
                or assignment.get("conditionVersion") not in (None, "")
                or assignment.get("delegatedManagedIdentityResourceId") not in (None, "")
                or role.get("roleName")
                != f"newsloom-{env['AZURE_ENV_NAME']}-agent-evaluation-{label}"
                or role.get("type") != "CustomRole"
                or role.get("assignableScopes") != [group_id(env)]
                or normalized_permissions(actual_permissions) != [expected]
                or output
                != {
                    "principal_id": env["AGENT_EVALUATION_OPERATOR_PRINCIPAL_ID"],
                    "principal_type": "User",
                    "scope": expected_scope,
                    "role_definition_id": definition_id,
                    **expected,
                }
            ):
                raise PlatformFailure("evaluation_verification_native_grant_mismatch")
            grants.pop(identifier)
            definitions.pop(definition_id)
    if (
        resources != before.get("resources")
        or projects != before.get("projects")
        or grants != before.get("grants")
        or definitions != before.get("definitions")
    ):
        raise PlatformFailure("evaluation_verification_unexpected_resource_or_authority")


def compare(
    before: dict[str, object], after: dict[str, object], env: dict[str, str], layer: str
) -> None:
    compare_authority(before, after, env, layer)
    old_data = json_object(before.get("stored_record"))
    new_data = json_object(after.get("stored_record"))
    if old_data.get("schema") == "news-metadata-v1":
        from newsloom_platform import evaluation_reconciliation

        evaluation_reconciliation.appended(old_data, new_data)
        return
    if timestamp(new_data.get("verified_utc")) <= timestamp(old_data.get("verified_utc")):
        raise PlatformFailure("evaluation_verification_independent_after_data_required")
    for key in ("news_count", "news_metadata_fingerprint", "recent_id_sha256", "recent_url_sha256"):
        if old_data.get(key) != new_data.get(key):
            raise PlatformFailure("evaluation_verification_stored_record_reconciliation_required")


def bound(
    value: dict[str, object],
    binding: dict[str, object],
    mode: str,
    *,
    admitted_at: float | None = None,
) -> None:
    if (
        value.get("outcome") != "success"
        or value.get("mode") != mode
        or any(value.get(key) != expected for key, expected in binding.items())
    ):
        raise PlatformFailure("evaluation_verification_evidence_binding_mismatch")
    if admitted_at is None:
        fresh(value.get("verified_utc"))
    elif not 0 <= admitted_at - timestamp(value.get("verified_utc")) <= 3600:
        raise PlatformFailure("evaluation_verification_stale_evidence")


def readback_correction(
    evidence: Evidence, manifest: Manifest, binding: dict[str, object]
) -> dict[str, object]:
    assert manifest.correction is not None
    correction = evidence.document(manifest.correction)
    if set(correction) != {"preservation", "intent", "completion", "failure", "account_after"}:
        raise PlatformFailure("evaluation_verification_invalid_correction")
    documents = {key: evidence.document(text_field(correction, key)) for key in correction}
    preserved = documents["preservation"]
    historical = json_object(preserved.get("source_files"))
    old_source = fingerprint(preserved.get("source_sha256"))
    current_files = source_files(evidence.root)
    allowed = {
        "services/platform/src/newsloom_platform/evaluation_verification.py",
        "services/platform/src/newsloom_platform/evaluation_reconciliation.py",
    }
    if (
        preserved.get("user_decision") != "approve_exact_project_bookkeeping"
        or digest(historical) != old_source
        or historical.keys() != current_files.keys()
        or old_source == binding["source_sha256"]
        or any(historical[name] != current_files[name] for name in historical.keys() - allowed)
    ):
        raise PlatformFailure("evaluation_verification_correction_source_mismatch")
    archive_path = text_field(preserved, "archive")
    raw = evidence.read(archive_path)
    if hashlib.sha256(raw).hexdigest() != preserved.get("archive_sha256"):
        raise PlatformFailure("evaluation_verification_correction_archive_mismatch")
    try:
        with ZipFile(io.BytesIO(raw)) as archive:
            if (
                len(archive.namelist()) != len(allowed)
                or set(archive.namelist()) != allowed
                or sum(item.file_size for item in archive.infolist()) > MAX_BYTES
                or any(
                    hashlib.sha256(archive.read(name)).hexdigest() != historical[name]
                    for name in allowed
                )
            ):
                raise PlatformFailure("evaluation_verification_correction_archive_mismatch")
    except BadZipFile:
        raise PlatformFailure("evaluation_verification_correction_archive_mismatch") from None
    intent, completion, failure = (documents[key] for key in ("intent", "completion", "failure"))
    historical_binding = {**binding, "source_sha256": old_source}
    assert (
        manifest.baseline is not None
        and manifest.plan is not None
        and manifest.review is not None
        and manifest.reconciliation is not None
    )
    plan_hash = hashlib.sha256(evidence.read(manifest.plan)).hexdigest()
    if (
        any(failure.get(key) != value for key, value in historical_binding.items())
        or failure.get("mode") != "readback"
        or failure.get("outcome") != "failure"
        or failure.get("category") != "evaluation_reconciliation_unreviewed_feature"
        or failure.get("baseline_sha256")
        != hashlib.sha256(evidence.read(manifest.baseline)).hexdigest()
        or failure.get("plan_sha256") != plan_hash
        or failure.get("plan_inventory") != evidence.document(manifest.review).get("plan_inventory")
        or failure.get("reconciliation_sha256")
        != hashlib.sha256(evidence.read(manifest.reconciliation)).hexdigest()
        or intent.get("approved_plan_sha256") != plan_hash
        or intent.get("source_sha256") != old_source
        or intent.get("layer") != "agent-evaluation"
        or intent.get("state_lock_enabled") is not True
        or intent.get("unknown_outcome_must_not_be_replayed") is not True
        or completion.get("source_sha256") != old_source
        or completion.get("azd_exit_code") != 0
        or completion.get("independent_readback_still_required") is not True
        or digest(account_invariant(documents["account_after"]))
        != json_object(failure.get("snapshot")).get("account")
    ):
        raise PlatformFailure("evaluation_verification_correction_lineage_mismatch")
    times = [
        timestamp(value.get(key))
        for value, key in (
            (intent, "recorded_utc"),
            (completion, "completed_utc"),
            (failure, "verified_utc"),
        )
    ]
    if times != sorted(times) or times[-1] > time.time():
        raise PlatformFailure("evaluation_verification_correction_chronology")
    return {
        "historical_source_sha256": old_source,
        "admitted_at": times[0],
        "account_after_sha256": json_object(failure.get("snapshot"))["account"],
        "inputs": {
            key: {
                "path": text_field(correction, key),
                "sha256": hashlib.sha256(evidence.read(text_field(correction, key))).hexdigest(),
            }
            for key in correction
        },
        "manifest_sha256": hashlib.sha256(evidence.read(manifest.correction)).hexdigest(),
    }


def binary_source(binary: bytes, owning_root: Path) -> None:
    expected = {f"tfconfig/m-/{path.name}": path for path in owning_root.glob("*.tf")}
    expected[".terraform.lock.hcl"] = owning_root / ".terraform.lock.hcl"
    lock = expected[".terraform.lock.hcl"].read_text()
    if not re.search(
        r'provider "registry\.terraform\.io/hashicorp/azurerm" \{\s+version\s+= "5\.10\.0"',
        lock,
    ):
        raise PlatformFailure("evaluation_verification_provider_lock_mismatch")
    try:
        with ZipFile(io.BytesIO(binary)) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)) or len(names) > 64:
                raise PlatformFailure("evaluation_verification_invalid_native_archive")
            source_names = {name for name in names if name.startswith("tfconfig/m-")}
            if source_names != set(expected) - {".terraform.lock.hcl"}:
                raise PlatformFailure("evaluation_verification_native_source_inventory")
            for name, path in expected.items():
                if (
                    name not in names
                    or archive.getinfo(name).file_size > 1024 * 1024
                    or archive.read(name) != path.read_bytes()
                ):
                    raise PlatformFailure("evaluation_verification_native_source_mismatch")
    except BadZipFile:
        raise PlatformFailure("evaluation_verification_native_binary_required") from None


def verify(env: dict[str, str], correlation: str, manifest_path: str) -> None:
    root = Path(control.run(["git", "rev-parse", "--show-toplevel"], "project_root"))
    evidence = Evidence(root, env["AZURE_ENV_NAME"])
    manifest = Manifest.model_validate(evidence.document(manifest_path))
    binding: dict[str, object] = {
        "layer": manifest.layer,
        "context_sha256": context(env),
        "source_sha256": source(root),
        "verification_scope": verification_scope(env),
    }
    output: dict[str, object] = {
        **binding,
        "mode": manifest.mode,
        "outcome": "success",
        "verified_utc": datetime.now(UTC).isoformat(),
    }
    if evidence.path(manifest.output).exists():
        raise PlatformFailure("evaluation_verification_output_already_exists")
    correction = (
        readback_correction(evidence, manifest, binding)
        if manifest.correction is not None
        else None
    )
    input_binding = dict(binding)
    admitted_at = None
    if correction is not None:
        input_binding["source_sha256"] = correction["historical_source_sha256"]
        admitted_at = float(str(correction["admitted_at"]))
        output["readback_correction"] = correction
    reader = Reader(env)
    if manifest.reconciliation is not None:
        from newsloom_platform import evaluation_reconciliation

        reader = evaluation_reconciliation.AccountReader(env)
    operator(reader, env)
    reconciliation: dict[str, object] | None = None
    if manifest.reconciliation is not None:
        from newsloom_platform import evaluation_reconciliation

        if correction is None:
            reconciliation = evaluation_reconciliation.receipt(
                evidence, manifest.reconciliation, env
            )
        else:
            reconciliation = evaluation_reconciliation.receipt(
                evidence,
                manifest.reconciliation,
                env,
                historical_source=fingerprint(correction["historical_source_sha256"]),
            )
        output["reconciliation_sha256"] = hashlib.sha256(
            evidence.read(manifest.reconciliation)
        ).hexdigest()
    elif (evidence.directory / "reconciliation-historical-preservation.json").exists():
        raise PlatformFailure("evaluation_verification_reconciliation_required")
    if manifest.mode == "baseline":
        assert manifest.stored_record is not None
        current = snapshot(reader, env)
        current["stored_record"] = stored_record(evidence, manifest.stored_record)
        if reconciliation is not None:
            if correction is not None and current["account"] != correction["account_after_sha256"]:
                raise PlatformFailure("evaluation_verification_correction_account_drift")
            evaluation_reconciliation.admit_snapshot(reconciliation, current, reader, env)
        output["snapshot"] = current
    else:
        assert manifest.baseline is not None and manifest.plan is not None
        baseline = evidence.document(manifest.baseline)
        bound(baseline, input_binding, "baseline", admitted_at=admitted_at)
        if baseline.get("reconciliation_sha256") != output.get("reconciliation_sha256"):
            raise PlatformFailure("evaluation_verification_reconciliation_binding_mismatch")
        output["baseline_sha256"] = hashlib.sha256(evidence.read(manifest.baseline)).hexdigest()
        binary = evidence.read(manifest.plan)
        output["plan_sha256"] = hashlib.sha256(binary).hexdigest()
        owning_root = root / (
            "infra" if manifest.layer == "application" else "infra/agent-evaluation"
        )
        binary_source(binary, owning_root)
        native = control.run(
            [
                "terraform",
                f"-chdir={owning_root}",
                "show",
                "-json",
                str(evidence.path(manifest.plan)),
            ],
            "evaluation_verification_native_plan",
            timeout=60,
        )
        if len(native.encode()) > MAX_BYTES or evidence.read(manifest.plan) != binary:
            raise PlatformFailure("evaluation_verification_changed_or_oversized_plan")
        plan = json_object(json.loads(native))
        if timestamp(plan.get("timestamp")) < timestamp(baseline.get("verified_utc")):
            raise PlatformFailure("evaluation_verification_plan_predates_baseline")
        output["plan_inventory"] = verify_plan(plan, env, manifest.layer, reviewed_at=admitted_at)
        retained_plan(plan, json_object(baseline.get("snapshot")), env, manifest.layer)
        output["account_prerequisites_ready"] = int(
            json_object(baseline.get("snapshot")).get("project_management") is True
            and bool(json_object(baseline.get("snapshot")).get("account_identity"))
        )
        if manifest.mode == "readback":
            assert manifest.review is not None and manifest.stored_record is not None
            review = evidence.document(manifest.review)
            bound(
                review,
                {
                    **input_binding,
                    **{
                        key: output[key]
                        for key in ("baseline_sha256", "plan_sha256", "plan_inventory")
                    },
                },
                "plan",
                admitted_at=admitted_at,
            )
            current = snapshot(reader, env)
            current["stored_record"] = stored_record(evidence, manifest.stored_record)
            output["snapshot"] = current
            try:
                previous = json_object(baseline.get("snapshot"))
                if (
                    manifest.layer == "agent-evaluation"
                    and not output["account_prerequisites_ready"]
                ):
                    if manifest.parent_readback is None:
                        raise PlatformFailure("evaluation_verification_parent_readback_required")
                    parent = evidence.document(manifest.parent_readback)
                    bound(parent, {**binding, "layer": "application"}, "readback")
                    fingerprint(parent.get("plan_sha256"))
                    fingerprint(parent.get("baseline_sha256"))
                    if json_object(parent.get("plan_inventory")).get("managed_resources") != 32:
                        raise PlatformFailure(
                            "evaluation_verification_parent_plan_evidence_required"
                        )
                    parent_snapshot = json_object(parent.get("snapshot"))
                    compare(previous, parent_snapshot, env, "application")
                    previous = parent_snapshot
                    output["parent_readback_sha256"] = hashlib.sha256(
                        evidence.read(manifest.parent_readback)
                    ).hexdigest()
                if reconciliation is not None:
                    previous, current = evaluation_reconciliation.metadata(
                        previous,
                        current,
                        env,
                        json_object(reconciliation["account_preimage"]),
                        evaluation_reconciliation.captured_account(reader),
                        project_bookkeeping=correction is not None,
                    )
                compare(previous, current, env, manifest.layer)
            except PlatformFailure as error:
                evidence.write(
                    manifest.output, {**output, "outcome": "failure", "category": str(error)}
                )
                raise
            if correction is not None:
                output["account_preimage"] = evaluation_reconciliation.captured_account(reader)
    if source(root) != binding["source_sha256"]:
        raise PlatformFailure("evaluation_verification_source_changed")
    if time.monotonic() > reader.deadline:
        raise PlatformFailure("evaluation_verification_metadata_limit")
    output["verified_utc"] = datetime.now(UTC).isoformat()
    output["metadata_reads"] = reader.calls
    evidence.write(manifest.output, output)
    event(
        "agent_evaluation_verification",
        "success",
        correlation,
        counts={
            "metadata_reads": reader.calls,
            "resource_mutations": 0,
            "model_calls": 0,
        },
    )
