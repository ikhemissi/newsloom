from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from newsloom_agent import cli
from newsloom_agent.generation import GenerationStats
from newsloom_agent.runtime import Config, application
from pydantic import ValidationError
from test_agent_delegation import Workload


@pytest.fixture
def runtime_environment() -> dict[str, str]:
    return {
        "AGENT_TENANT_ID": str(uuid4()),
        "AGENT_API_CLIENT_ID": str(uuid4()),
        "AZURE_CLIENT_ID": str(uuid4()),
        "MCP_API_CLIENT_ID": str(uuid4()),
        "AGENT_RESOURCE_URL": "https://agent.test/a2a",
        "MCP_RESOURCE_URL": "https://mcp.test/mcp",
        "MODEL_ENDPOINT": "https://owned.services.ai.azure.com/",
        "AGENT_CHAT_DEPLOYMENT": "existing-chat",
        "APPLICATIONINSIGHTS_CONNECTION_STRING": "PRIVATE_ROUTING_CANARY",
    }


def test_runtime_uses_only_explicit_trusted_configuration(
    runtime_environment: dict[str, str],
) -> None:
    config = Config.from_environment(runtime_environment)
    assert str(config.identity_client_id) == runtime_environment["AZURE_CLIENT_ID"]
    assert str(config.agent_client_id) == runtime_environment["AGENT_API_CLIENT_ID"]
    assert config.allowed_origins == ()
    assert not config.research_enabled
    assert config.scope == f"api://{runtime_environment['MCP_API_CLIENT_ID']}/.default"
    assert config.generation.deployment == "existing-chat"
    assert "PRIVATE_ROUTING_CANARY" not in repr(config)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("AGENT_RESOURCE_URL", "http://agent.test/a2a"),
        ("AGENT_RESOURCE_URL", "https://agent.test/a2a?untrusted=1"),
        ("AGENT_RESOURCE_URL", "https://agent.test/a2a/"),
        ("MCP_RESOURCE_URL", "http://mcp.test/mcp"),
        ("AGENT_ALLOWED_ORIGINS", "*"),
        ("AGENT_ALLOWED_ORIGINS", "https://*.untrusted.invalid"),
        ("AGENT_ALLOWED_ORIGINS", "https://untrusted.invalid/path"),
        ("AGENT_ALLOWED_ORIGINS", "https://trusted.test/"),
        ("AZURE_CLIENT_ID", "PRIVATE_ID_CANARY"),
        ("MODEL_ENDPOINT", "http://untrusted.invalid"),
        ("MODEL_ENDPOINT", "https://untrusted.invalid/path"),
        ("MODEL_ENDPOINT", "https://[PRIVATE_ENDPOINT_CANARY"),
        ("MODEL_ENDPOINT", "https://untrusted.invalid"),
        ("AGENT_CHAT_DEPLOYMENT", "https://untrusted.invalid"),
        ("APPLICATIONINSIGHTS_CONNECTION_STRING", ""),
        ("AGENT_RESEARCH_ENABLED", ""),
        ("AGENT_RESEARCH_ENABLED", "TRUE"),
        ("AGENT_RESEARCH_ENABLED", "1"),
        ("AGENT_RESEARCH_ENABLED", "yes"),
        ("AGENT_RESEARCH_ENABLED", "false "),
    ],
)
def test_invalid_runtime_configuration_never_creates_a_credential(
    runtime_environment: dict[str, str], field: str, value: str
) -> None:
    with pytest.raises(ValidationError):
        Config.from_environment({**runtime_environment, field: value})


@pytest.mark.parametrize("research", [False, True])
async def test_runtime_closes_own_mi_and_public_discovery_does_not_acquire_tokens(
    runtime_environment: dict[str, str], monkeypatch: pytest.MonkeyPatch, research: bool
) -> None:
    runtime_environment["AGENT_RESEARCH_ENABLED"] = str(research).lower()
    workload = Workload()
    selected: list[str] = []

    def credential(*, client_id: str) -> Workload:
        selected.append(client_id)
        return workload

    monkeypatch.setattr("newsloom_agent.runtime.ManagedIdentityCredential", credential)
    closed: list[bool] = []

    class LocalTelemetry:
        def __init__(self, routing: str, client_id: str) -> None:
            assert routing == runtime_environment["APPLICATIONINSIGHTS_CONNECTION_STRING"]
            assert client_id == runtime_environment["AZURE_CLIENT_ID"]

        def execution(
            self, outcome: str, category: str, elapsed: float, stats: GenerationStats
        ) -> None:
            raise AssertionError("public_routes_must_not_generate")

        def http(self, surface: str, outcome: str, elapsed: float) -> None:
            assert surface in ("a2a", "metadata", "health")

        def close(self) -> None:
            closed.append(True)

    monkeypatch.setattr("newsloom_agent.runtime.Telemetry", LocalTelemetry)
    config = Config.from_environment(runtime_environment)
    async with (
        application(config) as app,
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="https://agent.test"
        ) as http,
    ):
        assert (await http.get("/health/live")).status_code == 200
        card = await http.get("/.well-known/agent-card.json")
        assert card.status_code == 200 and card.json()["capabilities"]["streaming"]
        assert [skill["id"] for skill in card.json()["skills"]] == (
            ["recent-news", "research"] if research else ["recent-news"]
        )
        assert (await http.post("/a2a", json={})).status_code == 401
        assert workload.scopes == []
        assert selected == [runtime_environment["AZURE_CLIENT_ID"]]
    assert workload.closed
    assert closed == [True]


def test_serve_missing_configuration_is_safe_and_never_starts_a_server(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.argv", ["newsloom-agent", "serve"])
    monkeypatch.delenv("AGENT_TENANT_ID", raising=False)
    with pytest.raises(SystemExit, match="1"):
        cli.main()
    output = capsys.readouterr()
    assert "KeyError" in output.out
    assert "AGENT_TENANT_ID" not in output.out + output.err


def test_container_is_unprivileged_package_only_and_not_an_inspector_backdoor() -> None:
    root = Path(__file__).parents[1]
    dockerfile = (root / "services/agent/Dockerfile").read_text()
    assert "python:3.15.1-slim" in dockerfile
    assert "uv sync --locked --no-dev --package newsloom-agent" in dockerfile
    assert "USER 65532:65532" in dockerfile
    assert 'CMD ["serve"]' in dockerfile
    assert "azure-ai-agentserver" not in dockerfile
