import base64
import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import pytest
from newsloom_platform import agent_control, control
from newsloom_platform.config import PlatformFailure, json_object, text_field


@dataclass
class Deployment:
    env: dict[str, str]
    document: dict[str, object]


@pytest.fixture
def deployment(monkeypatch: pytest.MonkeyPatch) -> Deployment:
    tenant, subscription, client, principal, api, mcp = (str(uuid4()) for _ in range(6))
    group = f"/subscriptions/{subscription}/resourceGroups/rg-newsloom-test"
    identity = {
        "id": (
            f"{group}/providers/Microsoft.ManagedIdentity/"
            "userAssignedIdentities/id-newsloom-test-agent"
        ),
        "client_id": client,
        "principal_id": principal,
    }
    env = {
        "AGENT_ENABLED": "true",
        "AZURE_SUBSCRIPTION_ID": subscription,
        "AZURE_RESOURCE_GROUP": "rg-newsloom-test",
        "AZURE_ENV_NAME": "test",
        "AGENT_TENANT_ID": tenant,
        "AGENT_API_CLIENT_ID": api,
        "MCP_API_CLIENT_ID": mcp,
        "MCP_RESOURCE_URL": "https://mcp.test/mcp",
        "MODEL_ENDPOINT": "https://models.test/",
        "ENRICHMENT_DEPLOYMENT": "existing-chat",
        "APPLICATIONINSIGHTS_CONNECTION_STRING": "PRIVATE_ROUTING_CANARY",
        "AGENT_RESOURCE_URL": "https://agent.test/a2a",
        "AGENT_IMAGE": "test.azurecr.io/newsloom-agent@sha256:" + "1" * 64,
        "AGENT_IMAGE_REVISION": "2" * 64,
        "AZURE_CONTAINER_REGISTRY_ENDPOINT": "test.azurecr.io",
        "AGENT_IDENTITY_BASE64": base64.b64encode(json.dumps(identity).encode()).decode(),
        "AGENT_APP_ID": f"{group}/providers/Microsoft.App/containerApps/agent-newsloom-test",
        "AGENT_APP_NAME": "agent-newsloom-test",
        "AZURE_CONTAINER_APPS_ENVIRONMENT_ID": (
            f"{group}/providers/Microsoft.App/managedEnvironments/cae-newsloom-test"
        ),
    }
    values = {
        "AZURE_CLIENT_ID": client,
        "AGENT_TENANT_ID": tenant,
        "AGENT_API_CLIENT_ID": api,
        "AGENT_RESOURCE_URL": env["AGENT_RESOURCE_URL"],
        "AGENT_ALLOWED_ORIGINS": "",
        "AGENT_RUNTIME_REVISION": env["AGENT_IMAGE_REVISION"],
        "MCP_API_CLIENT_ID": mcp,
        "MCP_RESOURCE_URL": env["MCP_RESOURCE_URL"],
        "MODEL_ENDPOINT": env["MODEL_ENDPOINT"],
        "AGENT_CHAT_DEPLOYMENT": env["ENRICHMENT_DEPLOYMENT"],
        "APPLICATIONINSIGHTS_CONNECTION_STRING": env["APPLICATIONINSIGHTS_CONNECTION_STRING"],
    }
    document: dict[str, object] = {
        "id": env["AGENT_APP_ID"],
        "identity": {
            "type": "UserAssigned",
            "userAssignedIdentities": {
                identity["id"]: {"clientId": client, "principalId": principal}
            },
        },
        "properties": {
            "environmentId": env["AZURE_CONTAINER_APPS_ENVIRONMENT_ID"],
            "workloadProfileName": "Consumption",
            "provisioningState": "Succeeded",
            "latestRevisionName": "agent--ready",
            "latestReadyRevisionName": "agent--ready",
            "configuration": {
                "activeRevisionsMode": "Single",
                "ingress": {
                    "external": True,
                    "allowInsecure": False,
                    "targetPort": 8000,
                    "fqdn": "agent.test",
                },
                "registries": [{"server": "test.azurecr.io", "identity": identity["id"]}],
            },
            "template": {
                "scale": {"minReplicas": 1, "maxReplicas": 1},
                "containers": [
                    {
                        "name": "agent",
                        "image": env["AGENT_IMAGE"],
                        "resources": {"cpu": 0.25, "memory": "0.5Gi"},
                        "env": [{"name": key, "value": value} for key, value in values.items()],
                        "probes": [
                            {"type": name, "httpGet": {"port": 8000, "path": "/health/live"}}
                            for name in ("Startup", "Liveness", "Readiness")
                        ],
                    }
                ],
            },
        },
    }
    result = Deployment(env, document)
    monkeypatch.setattr(control, "rest", lambda url, category: result.document)
    return result


def test_default_disabled_app_preparer_never_builds_or_calls_azure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updates: dict[str, str] = {}
    monkeypatch.setattr(control, "set_environment", lambda key, value: updates.update({key: value}))
    agent_control.prepare({}, "local")
    assert updates["AGENT_ENABLED"] == "false"
    assert updates["AGENT_IMAGE"] == ""
    with pytest.raises(PlatformFailure, match="not_enabled"):
        agent_control.build({}, "local")


def test_preview_preparer_only_verifies_local_source_never_builds(
    deployment: Deployment, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(control, "source_hash", lambda root: "2" * 64)
    monkeypatch.setattr(control, "run", lambda arguments, category: "/tmp/agent-source-fixture")

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("preview_must_not_build_or_call_azure")

    monkeypatch.setattr(control, "build", forbidden)
    monkeypatch.setattr(control, "azure", forbidden)
    agent_control.prepare(deployment.env, "local")
    deployment.env["AGENT_IMAGE_REVISION"] = "3" * 64
    with pytest.raises(PlatformFailure, match="source_mismatch"):
        agent_control.prepare(deployment.env, "local")


def test_app_only_disable_preserves_identity_and_rollback_requires_matching_source(
    deployment: Deployment, monkeypatch: pytest.MonkeyPatch
) -> None:
    updates: dict[str, str] = {}
    monkeypatch.setattr(control, "set_environment", lambda key, value: updates.update({key: value}))
    deployment.env["AGENT_ENABLED"] = "false"
    agent_control.prepare(deployment.env, "local")
    assert updates == {"AGENT_ENABLED": "false"}
    deployment.env["AGENT_ENABLED"] = "true"
    deployment.env["AGENT_IMAGE_REVISION"] = "3" * 64
    monkeypatch.setattr(control, "run", lambda arguments, category: "/tmp/agent-source-fixture")
    monkeypatch.setattr(control, "source_hash", lambda root: "3" * 64)
    agent_control.prepare(deployment.env, "local")


def test_readback_proves_exact_owned_image_identity_config_and_profile(
    deployment: Deployment, capsys: pytest.CaptureFixture[str]
) -> None:
    baseline = deepcopy(deployment.document)
    agent_control.verify(deployment.env, "local")
    assert deployment.document == baseline
    output = capsys.readouterr().out
    assert "agent_deployment_readback" in output
    assert deployment.env["AGENT_API_CLIENT_ID"] not in output
    assert deployment.env["AGENT_RESOURCE_URL"] not in output
    assert deployment.env["AGENT_IMAGE_REVISION"] in output


@pytest.mark.parametrize("field", ["app", "identity", "environment", "registry", "all"])
def test_readback_accepts_equivalent_arm_path_casing(deployment: Deployment, field: str) -> None:
    properties = json_object(deployment.document["properties"])
    if field in ("app", "all"):
        deployment.document["id"] = deployment.env["AGENT_APP_ID"].lower()
    if field in ("identity", "all"):
        identity = json_object(deployment.document["identity"])
        assignments = json_object(identity["userAssignedIdentities"])
        key = next(iter(assignments))
        identity["userAssignedIdentities"] = {key.lower(): assignments[key]}
        deployment.document["identity"] = identity
    if field in ("environment", "all"):
        properties["environmentId"] = deployment.env["AZURE_CONTAINER_APPS_ENVIRONMENT_ID"].lower()
    if field in ("registry", "all"):
        configuration = json_object(properties["configuration"])
        registries = configuration["registries"]
        assert isinstance(registries, list)
        registry = json_object(registries[0])
        registries[0] = {**registry, "identity": text_field(registry, "identity").lower()}
        properties["configuration"] = configuration
    deployment.document["properties"] = properties
    agent_control.verify(deployment.env, "local")


@pytest.mark.parametrize("field", ["app", "identity", "environment", "registry"])
@pytest.mark.parametrize("suffix", ["/foreign", " ", "?foreign"])
def test_readback_rejects_non_equivalent_arm_paths(
    deployment: Deployment, field: str, suffix: str
) -> None:
    properties = json_object(deployment.document["properties"])
    if field == "app":
        deployment.document["id"] = deployment.env["AGENT_APP_ID"].lower() + suffix
    elif field == "identity":
        identity = json_object(deployment.document["identity"])
        assignments = json_object(identity["userAssignedIdentities"])
        key = next(iter(assignments))
        identity["userAssignedIdentities"] = {key.lower() + suffix: assignments[key]}
        deployment.document["identity"] = identity
    elif field == "environment":
        properties["environmentId"] = (
            deployment.env["AZURE_CONTAINER_APPS_ENVIRONMENT_ID"].lower() + suffix
        )
    else:
        configuration = json_object(properties["configuration"])
        registries = configuration["registries"]
        assert isinstance(registries, list)
        registry = json_object(registries[0])
        registries[0] = {
            **registry,
            "identity": text_field(registry, "identity").lower() + suffix,
        }
        properties["configuration"] = configuration
    deployment.document["properties"] = properties
    with pytest.raises(PlatformFailure):
        agent_control.verify(deployment.env, "local")


def test_readback_rejects_duplicate_identity_paths_with_different_casing(
    deployment: Deployment,
) -> None:
    identity = json_object(deployment.document["identity"])
    assignments = json_object(identity["userAssignedIdentities"])
    key = next(iter(assignments))
    assignments[key.lower()] = assignments[key]
    identity["userAssignedIdentities"] = assignments
    deployment.document["identity"] = identity
    with pytest.raises(PlatformFailure):
        agent_control.verify(deployment.env, "local")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provisioningState", "Failed"),
        ("latestReadyRevisionName", "old"),
        ("latestRevisionName", None),
        ("environmentId", "/foreign/environment"),
        ("workloadProfileName", "Dedicated"),
    ],
)
def test_unready_or_foreign_deployment_is_not_a_success(
    deployment: Deployment, field: str, value: object
) -> None:
    properties = json_object(deployment.document["properties"])
    properties[field] = value
    deployment.document["properties"] = properties
    with pytest.raises(PlatformFailure, match="readback_mismatch"):
        agent_control.verify(deployment.env, "local")


@pytest.mark.parametrize(
    "mismatch",
    [
        "image",
        "environment",
        "duplicate",
        "identity",
        "secret",
        "registry",
        "probes",
        "resources",
        "scale",
    ],
)
def test_readback_rejects_source_identity_config_and_probe_drift(
    deployment: Deployment, mismatch: str
) -> None:
    properties = json_object(deployment.document["properties"])
    template = json_object(properties["template"])
    containers = template["containers"]
    assert isinstance(containers, list)
    container = json_object(containers[0])
    if mismatch == "image":
        container["image"] = "test.azurecr.io/newsloom-mcp:latest"
    elif mismatch in ("environment", "duplicate", "secret"):
        values = container["env"]
        assert isinstance(values, list)
        if mismatch == "environment":
            values[0] = {**json_object(values[0]), "value": str(uuid4())}
        elif mismatch == "duplicate":
            values.append(values[0])
        else:
            values[0] = {**json_object(values[0]), "secretRef": "PRIVATE_SECRET_CANARY"}
    elif mismatch == "identity":
        deployment.document["identity"] = {
            **json_object(deployment.document["identity"]),
            "type": "SystemAssigned",
        }
    elif mismatch == "registry":
        properties["configuration"] = {**json_object(properties["configuration"]), "registries": []}
    elif mismatch == "probes":
        container["probes"] = []
    elif mismatch == "resources":
        container["resources"] = {"cpu": 1, "memory": "2Gi"}
    else:
        template["scale"] = {"minReplicas": 0, "maxReplicas": 10}
    containers[0] = container
    properties["template"] = template
    deployment.document["properties"] = properties
    with pytest.raises(PlatformFailure):
        agent_control.verify(deployment.env, "local")


def test_layer_preview_hook_has_no_build_and_has_separate_retained_state() -> None:
    root = Path(__file__).parents[1]
    yaml = (root / "azure.yaml").read_text()
    assert "newsloom-platform prepare-agent-layer" in yaml
    assert "newsloom-platform build-agent" not in yaml
    assert (
        '"key": "newsloom/${AZURE_ENV_NAME}-agent.tfstate"'
        in (root / "infra/agent/provider.conf.json").read_text()
    )
