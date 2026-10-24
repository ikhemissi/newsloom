import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

import httpx
import pytest
from azure.core.credentials import AccessToken
from azure.identity.aio import ManagedIdentityCredential
from newsloom_core.model_transport import Vector
from newsloom_mcp import cli, verification
from newsloom_mcp.app import Services
from newsloom_mcp.auth import EntraVerifier
from newsloom_mcp.models import McpFailure
from newsloom_mcp.repository import NewsRepository, Repository
from newsloom_mcp.runtime import Config
from newsloom_platform import database
from newsloom_platform.config import RuntimeConfig
from psycopg import sql
from test_mcp_database import repository as repository
from test_platform_database import platform_database as platform_database


@pytest.fixture
def config() -> Config:
    return Config(
        tenant=uuid4(),
        audience=uuid4(),
        client_id=uuid4(),
        resource_url="https://newsloom.test/mcp",
        postgres_host="localhost",
        postgres_database="newsloom",
        model_endpoint="https://models.test",
        embedding_deployment="embedding",
        embedding_model="embedding-test",
        embedding_version="1",
        telemetry_routing="synthetic",
    )


class Credential:
    async def get_token(self, *scopes: str, **kwargs: object) -> AccessToken:
        return AccessToken(
            "API_CREDENTIAL_CANARY"
            if scopes[0].startswith("api://")
            else "MODEL_CREDENTIAL_CANARY",
            9999999999,
        )

    async def close(self) -> None:
        return None

    async def __aenter__(self) -> Credential:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()


def handler(request: httpx.Request) -> httpx.Response:
    if request.url.host == "models.test":
        assert set(json.loads(request.content)) == {"model"}
        assert request.headers["Authorization"] == "Bearer MODEL_CREDENTIAL_CANARY"
        return httpx.Response(403)
    status = 403 if request.headers.get("Authorization") == "Bearer API_CREDENTIAL_CANARY" else 401
    return httpx.Response(status)


async def test_signed_scope_and_resource_checks_do_not_forward_api_credentials_to_models(
    config: Config,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        counts = await verification.verify_http(
            config, Credential(), client, "generation", "screening"
        )
    assert counts == {
        "anonymous_denials": 1,
        "wrong_resource_denials": 1,
        "model_denials": 2,
        "app_only_denials": 3,
    }
    output = capsys.readouterr()
    assert "CANARY" not in output.out + output.err


@pytest.mark.parametrize("status", [200, 400, 404, 429, 500])
async def test_http_errors_or_success_are_not_authorization_denials(
    config: Config, status: int
) -> None:
    def wrong(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status) if request.url.host == "models.test" else handler(request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(wrong)) as client:
        with pytest.raises(McpFailure, match="model_denial_not_proven"):
            await verification.verify_http(config, Credential(), client, "generation", "screening")


@pytest.mark.parametrize("status", [200, 401])
async def test_app_only_claim_validation_requires_insufficient_scope_not_just_any_error(
    config: Config,
    status: int,
) -> None:
    def wrong(request: httpx.Request) -> httpx.Response:
        if request.headers.get("Authorization") == "Bearer API_CREDENTIAL_CANARY":
            return httpx.Response(status)
        return handler(request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(wrong)) as client:
        with pytest.raises(McpFailure, match="app_only_denial_not_proven"):
            await verification.verify_http(config, Credential(), client, "generation", "screening")


@pytest.mark.integration
async def test_verifier_checks_real_records_and_acl_denials_not_readonly_rejection(
    repository: Repository,
) -> None:
    async with repository.connection.transaction():
        await repository.connection.execute(
            "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
        )
        args, counts = await verification.verify_news(repository, uuid4().hex)
        assert counts == {"news": 12, "recent_ids": 5, "cleanup_checks": 1}
        assert args.from_ is not None and len(args.tags) == 2
    async with repository.connection.transaction():
        await repository.connection.execute("SET TRANSACTION READ ONLY")
        assert await verification.verify_database_denials(repository) == 10
        assert await (
            await repository.connection.execute("SHOW transaction_read_only")
        ).fetchone() == ("off",)
    assert await (
        await repository.connection.execute(
            "SELECT to_regnamespace('newsloom_mcp_permission_probe')"
        )
    ).fetchone() == (None,)


@pytest.mark.integration
async def test_unexpected_write_or_ddl_grant_rolls_back_before_failing(
    repository: Repository,
    platform_database: RuntimeConfig,
) -> None:
    async with (
        ManagedIdentityCredential() as credential,
        await database.connect(platform_database, credential, "newsloom", "postgres") as admin,
    ):
        name = "probe_" + uuid4().hex
        with pytest.raises(McpFailure, match="denial_not_proven"):
            await verification.require_denied(
                admin, sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(name))
            )
        assert (
            await (
                await admin.execute("SELECT 1 FROM pg_namespace WHERE nspname=%s", (name,))
            ).fetchone()
            is None
        )
        before = await (await admin.execute("SELECT id,title FROM news ORDER BY id")).fetchall()
        with pytest.raises(McpFailure, match="denial_not_proven"):
            await verification.require_denied(
                admin, sql.SQL("UPDATE news SET title='NEWSLOOM_CONTENT_CANARY'")
            )
        after = await (await admin.execute("SELECT id,title FROM news ORDER BY id")).fetchall()
        assert before == after and len(after) == 12


@pytest.mark.integration
async def test_verifier_fails_when_evaluation_schema_is_still_present(
    repository: Repository,
    platform_database: RuntimeConfig,
) -> None:
    run_id = uuid4().hex
    name = "mcp_eval_" + run_id
    async with (
        ManagedIdentityCredential() as credential,
        await database.connect(platform_database, credential, "newsloom", "postgres") as admin,
    ):
        await admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(name)))
        try:
            with pytest.raises(McpFailure, match="evaluation_schema_still_present"):
                await verification.verify_news(repository, run_id)
        finally:
            await admin.execute(sql.SQL("DROP SCHEMA {}").format(sql.Identifier(name)))


@pytest.mark.integration
async def test_complete_private_verifier_uses_real_sql_without_cloud_credentials(
    repository: Repository,
    config: Config,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Embedding:
        async def embed(self, query: str, deadline: float) -> Vector:
            return Vector(values=(0.1,) * 1536)

    @asynccontextmanager
    async def repositories() -> AsyncIterator[NewsRepository]:
        async with repository.connection.transaction():
            await repository.connection.execute(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
            )
            yield repository

    async def ready() -> bool:
        return True

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:

        @asynccontextmanager
        async def resources(
            current: Config,
            *,
            instrument: bool,
        ) -> AsyncIterator[tuple[Services, EntraVerifier]]:
            assert current == config and not instrument
            yield (
                Services(repositories, Embedding(), ready),
                EntraVerifier(client, config.tenant, config.audience),
            )

        monkeypatch.setattr(verification, "resources", resources)
        monkeypatch.setattr(
            verification, "ManagedIdentityCredential", lambda **kwargs: Credential()
        )

        @asynccontextmanager
        async def http_client(**kwargs: object) -> AsyncIterator[httpx.AsyncClient]:
            yield client

        monkeypatch.setattr(httpx, "AsyncClient", http_client)
        counts = await verification.verify_access(config, "generation", "screening", uuid4().hex)
    assert counts == {
        "news": 12,
        "recent_ids": 5,
        "cleanup_checks": 1,
        "database_denials": 10,
        "anonymous_denials": 1,
        "wrong_resource_denials": 1,
        "model_denials": 2,
        "app_only_denials": 3,
        "tool_checks": 5,
        "embedding_dimensions": 1536,
    }


def test_private_cli_rejects_missing_parameters_without_configuration_or_network(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("sys.argv", ["newsloom-mcp", "verify-access"])
    with pytest.raises(SystemExit) as result:
        cli.main()
    assert result.value.code == 1
    assert json.loads(capsys.readouterr().out)["category"] == "verification_deployments_required"


def test_private_cli_emits_only_safe_failure_categories(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    config: Config,
) -> None:
    async def failed(*args: object, **kwargs: object) -> dict[str, int]:
        raise httpx.ConnectError("NEWSLOOM_CREDENTIAL_CANARY")

    monkeypatch.setattr(
        "sys.argv",
        [
            "newsloom-mcp",
            "verify-access",
            "--generation-deployment",
            "generation",
            "--screening-deployment",
            "screening",
        ],
    )
    monkeypatch.setattr(Config, "environment", lambda: config)
    monkeypatch.setattr(verification, "verify_access", failed)
    with pytest.raises(SystemExit) as result:
        cli.main()
    assert result.value.code == 1
    output = capsys.readouterr()
    assert json.loads(output.out)["category"] == "ConnectError"
    assert "CANARY" not in output.out + output.err
