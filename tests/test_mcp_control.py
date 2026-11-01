import base64
import json
from copy import deepcopy
from uuid import uuid4

import pytest
from newsloom_platform import control, mcp_control
from newsloom_platform.config import PlatformFailure, json_object
from test_ui_control import UiCase
from test_ui_control import ui_case as ui_case


@pytest.fixture
def mcp_case(ui_case: UiCase, monkeypatch: pytest.MonkeyPatch) -> UiCase:
    env = dict(ui_case.env)
    group = (
        f"/subscriptions/{env['AZURE_SUBSCRIPTION_ID']}"
        f"/resourceGroups/{env['AZURE_RESOURCE_GROUP']}"
    )
    identity = {
        "id": (
            f"{group}/providers/Microsoft.ManagedIdentity"
            "/userAssignedIdentities/id-newsloom-test-mcp"
        ),
        "client_id": str(uuid4()),
        "principal_id": str(uuid4()),
    }
    env.update(
        {
            "MCP_APP_ID": f"{group}/providers/Microsoft.App/containerApps/mcp-newsloom-test",
            "MCP_APP_NAME": "mcp-newsloom-test",
            "MCP_TENANT_ID": env["AGENT_TENANT_ID"],
            "MCP_API_CLIENT_ID": str(uuid4()),
            "MCP_RESOURCE_URL": "https://mcp.test/mcp",
            "MCP_ALLOWED_ORIGINS": "https://ui.test",
            "MCP_IMAGE": env["WEB_IMAGE"].replace("newsloom-web", "newsloom-mcp"),
            "MCP_IMAGE_REVISION": "2" * 64,
            "WORKLOAD_IDENTITIES_BASE64": base64.b64encode(
                json.dumps({"mcp": identity}).encode()
            ).decode(),
            "POSTGRES_HOST": "postgres.test",
            "POSTGRES_DATABASE": "newsloom",
            "MODEL_ENDPOINT": "https://model.test/",
            "EMBEDDINGS_DEPLOYMENT": "existing-embeddings",
            "EMBEDDINGS_MODEL": "existing-model",
            "EMBEDDINGS_VERSION": "existing-version",
            "APPLICATIONINSIGHTS_CONNECTION_STRING": "PRIVATE_ROUTING_CANARY",
        }
    )
    app = deepcopy(ui_case.app)
    app["id"] = env["MCP_APP_ID"]
    app["identity"] = {
        "type": "UserAssigned",
        "userAssignedIdentities": {
            identity["id"]: {
                "clientId": identity["client_id"],
                "principalId": identity["principal_id"],
            }
        },
    }
    properties = json_object(app["properties"])
    configuration = json_object(properties["configuration"])
    configuration["registries"] = [
        {
            "server": env["AZURE_CONTAINER_REGISTRY_ENDPOINT"],
            "identity": identity["id"],
        }
    ]
    configuration["ingress"] = {
        "external": True,
        "allowInsecure": False,
        "targetPort": 8000,
        "fqdn": "mcp.test",
    }
    keys = (
        "MCP_TENANT_ID",
        "MCP_API_CLIENT_ID",
        "MCP_RESOURCE_URL",
        "MCP_ALLOWED_ORIGINS",
        "POSTGRES_HOST",
        "POSTGRES_DATABASE",
        "MODEL_ENDPOINT",
        "EMBEDDINGS_DEPLOYMENT",
        "EMBEDDINGS_MODEL",
        "EMBEDDINGS_VERSION",
        "APPLICATIONINSIGHTS_CONNECTION_STRING",
    )
    properties["template"] = {
        "scale": {"minReplicas": 1, "maxReplicas": 1},
        "containers": [
            {
                "name": "mcp",
                "image": env["MCP_IMAGE"],
                "resources": {"cpu": 0.25, "memory": "0.5Gi"},
                "env": [{"name": "AZURE_CLIENT_ID", "value": identity["client_id"]}]
                + [{"name": key, "value": env[key]} for key in keys],
            }
        ],
    }
    properties["configuration"] = configuration
    app["properties"] = properties
    monkeypatch.setattr(control, "rest", lambda *args: app)
    return UiCase(env, app, {}, [])


def test_mcp_browser_readback_is_exact_and_content_free(
    mcp_case: UiCase,
    capsys: pytest.CaptureFixture[str],
) -> None:
    mcp_control.verify(mcp_case.env, "local")
    output = capsys.readouterr().out
    assert "mcp_deployment_readback" in output
    assert mcp_case.env["MCP_API_CLIENT_ID"] not in output
    assert "PRIVATE_ROUTING_CANARY" not in output


@pytest.mark.parametrize("key", ["MCP_IMAGE", "MCP_ALLOWED_ORIGINS", "EMBEDDINGS_DEPLOYMENT"])
def test_mcp_image_origin_or_model_drift_is_rejected(mcp_case: UiCase, key: str) -> None:
    env = {
        **mcp_case.env,
        key: (
            mcp_case.env[key].replace("1", "3")
            if key == "MCP_IMAGE"
            else "https://other.test"
            if key == "MCP_ALLOWED_ORIGINS"
            else "foreign-model"
        ),
    }
    with pytest.raises(PlatformFailure):
        mcp_control.verify(env, "local")


def test_mcp_preparation_preserves_source_bound_encoded_origins(
    mcp_case: UiCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updates: dict[str, str] = {}
    monkeypatch.setattr(control, "run", lambda *args: "/tmp/authored-source")
    monkeypatch.setattr(control, "source_hash", lambda _: "2" * 64)
    monkeypatch.setattr(control, "set_environment", lambda key, value: updates.update({key: value}))
    mcp_control.prepare(mcp_case.env, "local")
    assert json.loads(base64.b64decode(updates["MCP_ALLOWED_ORIGINS_BASE64"])) == [
        "https://ui.test"
    ]
    with pytest.raises(PlatformFailure, match="invalid_mcp_allowed_origins"):
        mcp_control.prepare({**mcp_case.env, "MCP_ALLOWED_ORIGINS": "https://ui.test,"}, "local")
