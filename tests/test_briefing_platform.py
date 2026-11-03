import base64
import json
from copy import deepcopy
from typing import Any
from uuid import uuid4

import pytest
from newsloom_platform import briefing, control, mcp_control
from newsloom_platform.config import PlatformFailure


@pytest.fixture
def briefing_case(monkeypatch: pytest.MonkeyPatch) -> tuple[dict[str, str], dict[str, Any]]:
    group = "/subscriptions/test/resourceGroups/rg-newsloom-test"
    env = {
        "AZURE_SUBSCRIPTION_ID": "test",
        "AZURE_RESOURCE_GROUP": "rg-newsloom-test",
        "AZURE_ENV_NAME": "test",
        "AZURE_LOCATION": "francecentral",
        "AZURE_CONTAINER_APPS_ENVIRONMENT_ID": (
            f"{group}/providers/Microsoft.App/managedEnvironments/existing"
        ),
        "AZURE_CONTAINER_REGISTRY_ENDPOINT": "test.azurecr.io",
        "AZURE_CONTAINER_REGISTRY_ID": (
            f"{group}/providers/Microsoft.ContainerRegistry/registries/test"
        ),
        "APPLICATIONINSIGHTS_ID": f"{group}/providers/Microsoft.Insights/components/test",
        "BRIEFING_ENABLED": "true",
        "BRIEFING_SCHEDULE_ENABLED": "false",
        "BRIEFING_DEPLOYMENT": "briefing",
        "MODEL_ACCOUNT_ID": f"{group}/providers/Microsoft.CognitiveServices/accounts/models",
        "MODEL_ENDPOINT": "https://model.test",
        "ENRICHMENT_MODEL": "pinned-model",
        "ENRICHMENT_VERSION": "pinned-version",
        "ENRICHMENT_SKU": "Standard",
        "ENRICHMENT_DEPLOYMENT": "enrichment",
        "POSTGRES_HOST": "test.postgres.database.azure.com",
        "POSTGRES_DATABASE": "newsloom",
        "BRIEFING_INPUT_PRICE_PER_MILLION": "0.1",
        "BRIEFING_OUTPUT_PRICE_PER_MILLION": "0.2",
        "BRIEFING_PRICE_BASIS": "2026-11-02 test fixture not a live verified price",
        "BRIEFING_IMAGE": "test.azurecr.io/newsloom-briefing@sha256:" + "a" * 64,
        "BRIEFING_IMAGE_REVISION": "b" * 64,
        "BRIEFING_JOB_ID": f"{group}/providers/Microsoft.App/jobs/brief-newsloom-test",
        "APPLICATIONINSIGHTS_CONNECTION_STRING": "PRIVATE_ROUTING_CANARY",
    }
    selected = {
        "id": (
            f"{group}/providers/Microsoft.ManagedIdentity"
            "/userAssignedIdentities/id-newsloom-test-briefing"
        ),
        "client_id": str(uuid4()),
        "principal_id": str(uuid4()),
    }
    env["BRIEFING_IDENTITY_BASE64"] = base64.b64encode(json.dumps(selected).encode()).decode()
    env["WORKLOAD_IDENTITIES_BASE64"] = base64.b64encode(
        json.dumps(
            {
                name: {
                    "id": f"{group}/{name}",
                    "client_id": str(uuid4()),
                    "principal_id": str(uuid4()),
                }
                for name in ("ingestion", "enrichment", "mcp", "migrations")
            }
        ).encode()
    ).decode()
    model = {
        "id": f"{env['MODEL_ACCOUNT_ID']}/deployments/briefing",
        "name": "briefing",
        "properties": {
            "model": {"format": "OpenAI", "name": "pinned-model", "version": "pinned-version"},
            "versionUpgradeOption": "NoAutoUpgrade",
        },
        "sku": {"name": "Standard", "capacity": 10},
    }
    retained = deepcopy(model)
    retained.update(id=f"{env['MODEL_ACCOUNT_ID']}/deployments/enrichment", name="enrichment")
    job = {
        "location": "francecentral",
        "identity": {
            "type": "UserAssigned",
            "userAssignedIdentities": {
                selected["id"]: {
                    "clientId": selected["client_id"],
                    "principalId": selected["principal_id"],
                }
            },
        },
        "properties": {
            "provisioningState": "Succeeded",
            "environmentId": env["AZURE_CONTAINER_APPS_ENVIRONMENT_ID"],
            "workloadProfileName": "Consumption",
            "configuration": {
                "replicaTimeout": 3600,
                "replicaRetryLimit": 0,
                "triggerType": "Manual",
                "manualTriggerConfig": {"parallelism": 1, "replicaCompletionCount": 1},
                "registries": [{"server": "test.azurecr.io", "identity": selected["id"]}],
            },
            "template": {
                "containers": [
                    {
                        "image": env["BRIEFING_IMAGE"],
                        "args": ["run"],
                        "resources": {"cpu": 0.5, "memory": "1Gi"},
                        "env": [
                            {"name": key, "value": value}
                            for key, value in briefing.expected_environment(env).items()
                        ],
                    }
                ]
            },
        },
    }
    role = "/subscriptions/test/providers/Microsoft.Authorization/roleDefinitions/chat"
    grants = [
        {
            "properties": {
                "scope": env[key],
                "roleDefinitionId": f"/role/{identifier}",
                "principalId": selected["principal_id"],
                "principalType": "ServicePrincipal",
            }
        }
        for key, identifier in (
            ("AZURE_CONTAINER_REGISTRY_ID", briefing.ACR_PULL_ROLE),
            ("APPLICATIONINSIGHTS_ID", briefing.METRICS_ROLE),
        )
    ]
    grants.append(
        {
            "properties": {
                "scope": env["MODEL_ACCOUNT_ID"],
                "roleDefinitionId": role,
                "principalId": selected["principal_id"],
                "principalType": "ServicePrincipal",
            }
        }
    )
    documents = {
        "job": job,
        "model": model,
        "retained": retained,
        "identity": {
            "id": selected["id"],
            "location": "francecentral",
            "properties": {
                "clientId": selected["client_id"],
                "principalId": selected["principal_id"],
            },
        },
        "grants": {"value": grants},
        "chat_role": {
            "properties": {
                "type": "CustomRole",
                "roleName": "newsloom-test-briefing-chat",
                "assignableScopes": [group],
                "permissions": [{"dataActions": [briefing.CHAT_ACTION], "actions": []}],
            }
        },
    }

    def rest(url: str, category: str) -> object:
        if category == "briefing_job_readback":
            return documents["job"]
        if category == "briefing_preservation_inventory":
            return {"value": [documents["model"], documents["retained"]]}
        if category == "briefing_identity_readback":
            return documents["identity"]
        if category == "briefing_grant_inventory":
            return documents["grants"]
        if category == "briefing_chat_role_readback":
            return documents["chat_role"]
        return documents["model"]

    monkeypatch.setattr(control, "rest", rest)
    monkeypatch.setattr(control, "source_hash", lambda root: "b" * 64)
    monkeypatch.setattr(control, "run", lambda *args, **kwargs: ".")
    env["BRIEFING_PRESERVATION_SHA256"] = briefing.preservation(env)
    return env, documents


def test_default_off_preparation_does_not_read_azure_or_build(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writes = {}
    monkeypatch.setattr(control, "set_environment", lambda key, value: writes.update({key: value}))
    monkeypatch.setattr(control, "rest", lambda *args, **kwargs: pytest.fail("Azure read"))
    monkeypatch.setattr(control, "build", lambda *args, **kwargs: pytest.fail("build"))
    briefing.prepare_identity({}, "test")
    briefing.prepare({}, "test")
    assert writes["BRIEFING_ENABLED"] == writes["BRIEFING_SCHEDULE_ENABLED"] == "false"
    assert writes["NEWS_BRIEFING_ENABLED"] == "false"
    assert writes["BRIEFING_IDENTITY_BASE64"] == ""


@pytest.mark.parametrize("location", ["francecentral", "France Central"])
def test_verify_manual_and_scheduled(
    briefing_case: tuple[dict[str, str], dict[str, Any]], location: str
) -> None:
    env, documents = briefing_case
    documents["job"]["location"] = location
    briefing.verify(env, "test")
    env["BRIEFING_SCHEDULE_ENABLED"] = "true"
    config = documents["job"]["properties"]["configuration"]
    config["triggerType"] = "Schedule"
    config["scheduleTriggerConfig"] = {
        "parallelism": 1,
        "replicaCompletionCount": 1,
        "cronExpression": "0 5 * * *",
    }
    briefing.verify(env, "test")
    config["scheduleTriggerConfig"]["cronExpression"] = "*/5 * * * *"
    with pytest.raises(PlatformFailure, match="configuration_mismatch"):
        briefing.verify(env, "test")


@pytest.mark.parametrize(
    "key,value",
    [
        ("replicaTimeout", 900),
        ("replicaRetryLimit", 1),
        ("triggerType", "Schedule"),
    ],
)
def test_verify_rejects_job_drift(
    briefing_case: tuple[dict[str, str], dict[str, Any]],
    key: str,
    value: object,
) -> None:
    env, documents = briefing_case
    documents["job"]["properties"]["configuration"][key] = value
    with pytest.raises(PlatformFailure, match="configuration_mismatch"):
        briefing.verify(env, "test")


@pytest.mark.parametrize("location", ["North Europe", None, "France-Central"])
def test_verify_rejects_different_or_invalid_job_region(
    briefing_case: tuple[dict[str, str], dict[str, Any]], location: object
) -> None:
    env, documents = briefing_case
    documents["job"]["location"] = location
    with pytest.raises(PlatformFailure, match="configuration_mismatch"):
        briefing.verify(env, "test")


def test_verify_rejects_existing_resource_or_model_drift(
    briefing_case: tuple[dict[str, str], dict[str, Any]],
) -> None:
    env, documents = briefing_case
    documents["retained"]["sku"]["capacity"] = 20
    with pytest.raises(PlatformFailure, match="retained_resources_changed"):
        briefing.verify(env, "test")
    documents["retained"]["sku"]["capacity"] = 10
    documents["model"]["sku"]["capacity"] = 20
    with pytest.raises(PlatformFailure, match="model_contract_mismatch"):
        briefing.verify(env, "test")


@pytest.mark.parametrize("price", ["", "-1", "NaN", "Infinity"])
def test_unknown_or_invalid_price_is_not_zero(
    briefing_case: tuple[dict[str, str], dict[str, Any]],
    price: str,
) -> None:
    env, _ = briefing_case
    env["BRIEFING_INPUT_PRICE_PER_MILLION"] = price
    with pytest.raises(PlatformFailure, match="verified_prices_required"):
        briefing.prices(env)


def test_own_identity_cannot_reuse_foundation(
    briefing_case: tuple[dict[str, str], dict[str, Any]],
) -> None:
    env, _ = briefing_case
    foundation = json.loads(base64.b64decode(env["WORKLOAD_IDENTITIES_BASE64"]))
    own = json.loads(base64.b64decode(env["BRIEFING_IDENTITY_BASE64"]))
    foundation["mcp"]["principal_id"] = own["principal_id"]
    env["WORKLOAD_IDENTITIES_BASE64"] = base64.b64encode(json.dumps(foundation).encode()).decode()
    with pytest.raises(PlatformFailure, match="identity_not_isolated"):
        briefing.identity(env)


def test_readback_rejects_broader_model_authority(
    briefing_case: tuple[dict[str, str], dict[str, Any]],
) -> None:
    env, documents = briefing_case
    documents["chat_role"]["properties"]["permissions"][0]["dataActions"].append(
        "Microsoft.CognitiveServices/accounts/OpenAI/deployments/embeddings/action"
    )
    with pytest.raises(PlatformFailure, match="chat_role_mismatch"):
        briefing.verify(env, "test")


def test_readback_rejects_extra_grants(
    briefing_case: tuple[dict[str, str], dict[str, Any]],
) -> None:
    env, documents = briefing_case
    documents["grants"]["value"].append(deepcopy(documents["grants"]["value"][0]))
    with pytest.raises(PlatformFailure, match="grant_inventory_mismatch"):
        briefing.verify(env, "test")


def test_briefing_read_flag_is_separate_and_requires_api() -> None:
    assert mcp_control.briefing_enabled({}) == "false"
    assert (
        mcp_control.briefing_enabled(
            {
                "NEWS_API_ENABLED": "true",
                "NEWS_BRIEFING_ENABLED": "true",
            }
        )
        == "true"
    )
    with pytest.raises(PlatformFailure, match="requires_news_api"):
        mcp_control.briefing_enabled({"NEWS_BRIEFING_ENABLED": "true"})


def test_prepare_builds_only_after_readback_and_preserves_manifest(
    briefing_case: tuple[dict[str, str], dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env, _ = briefing_case
    before = env["WORKLOAD_IDENTITIES_BASE64"]
    writes = {}
    built = []
    monkeypatch.setattr(control, "set_environment", lambda key, value: writes.update({key: value}))
    monkeypatch.setattr(
        control, "build", lambda env, correlation, *, service: built.append(service)
    )
    briefing.prepare_identity(env, "test")
    briefing.prepare(env, "test")
    assert built == ["briefing"]
    assert env["WORKLOAD_IDENTITIES_BASE64"] == before
    assert "WORKLOAD_IDENTITIES_BASE64" not in writes
    assert writes["BRIEFING_PRESERVATION_SHA256"] == env["BRIEFING_PRESERVATION_SHA256"]


def test_manual_execution_verifies_first_and_reads_only_safe_counts(
    briefing_case: tuple[dict[str, str], dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env, _ = briefing_case
    env["MIGRATION_JOB_ID"] = "/migration/job"
    calls = []
    writes = {}
    monkeypatch.setattr(control, "set_environment", lambda key, value: writes.update({key: value}))

    def execute(job: str, correlation: str, **kwargs: object) -> str:
        calls.append((job, kwargs))
        return "safe-execution-name"

    monkeypatch.setattr(control, "execute_job", execute)
    briefing.control("execute-briefing", env, "test")
    assert calls == [
        (env["BRIEFING_JOB_ID"], {"wait_seconds": 3660}),
        ("/migration/job", {"arguments": ["briefing-status"]}),
    ]
    assert writes == {"BRIEFING_LAST_EXECUTION": "safe-execution-name"}


def test_verified_retail_price_basis(
    briefing_case: tuple[dict[str, str], dict[str, Any]],
) -> None:
    env, _ = briefing_case
    env["BRIEFING_PRICE_BASIS"] = "AzureRetail-2026-11-02-francecentral-DataZoneStandard"
    briefing.prices(env)
