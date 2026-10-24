"""Workload-only connections and resources; no caller token is accepted here."""

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Literal
from uuid import UUID

import httpx
import psycopg
from azure.identity.aio import ManagedIdentityCredential
from newsloom_core.model_transport import ModelClient, TransportLimits
from pydantic import BaseModel, ConfigDict, Field, model_validator
from starlette.applications import Starlette

from newsloom_mcp.app import Services, create_app
from newsloom_mcp.auth import EntraVerifier
from newsloom_mcp.embedding import FoundryQueryEmbedding
from newsloom_mcp.repository import NewsRepository, Repository
from newsloom_mcp.telemetry import Telemetry


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    tenant: UUID
    audience: UUID
    client_id: UUID
    resource_url: Annotated[str, Field(pattern=r"^https://[^/?#]+/mcp$")]
    postgres_host: str
    postgres_database: Literal["newsloom"]
    model_endpoint: str
    embedding_deployment: str
    embedding_model: str
    embedding_version: str
    telemetry_routing: str
    allowed_origins: tuple[str, ...] = ()

    @model_validator(mode="after")
    def canonical_origin(self) -> Config:
        url = httpx.URL(self.resource_url)
        if (
            url.userinfo
            or url.query
            or url.fragment
            or url.port not in (None, 443)
            or not url.host
            or url.path != "/mcp"
        ):
            raise ValueError("invalid_mcp_resource_url")
        return self

    @classmethod
    def environment(cls) -> Config:
        env = os.environ
        return cls.model_validate(
            {
                "tenant": env["MCP_TENANT_ID"],
                "audience": env["MCP_API_CLIENT_ID"],
                "client_id": env["AZURE_CLIENT_ID"],
                "resource_url": env["MCP_RESOURCE_URL"],
                "postgres_host": env["POSTGRES_HOST"],
                "postgres_database": env["POSTGRES_DATABASE"],
                "model_endpoint": env["MODEL_ENDPOINT"],
                "embedding_deployment": env["EMBEDDINGS_DEPLOYMENT"],
                "embedding_model": env["EMBEDDINGS_MODEL"],
                "embedding_version": env["EMBEDDINGS_VERSION"],
                "telemetry_routing": env["APPLICATIONINSIGHTS_CONNECTION_STRING"],
                "allowed_origins": tuple(
                    item for item in env.get("MCP_ALLOWED_ORIGINS", "").split(",") if item
                ),
            }
        )


@asynccontextmanager
async def resources(
    config: Config, *, instrument: bool = True
) -> AsyncIterator[tuple[Services, EntraVerifier]]:
    async with (
        ManagedIdentityCredential(client_id=str(config.client_id)) as credential,
        httpx.AsyncClient() as client,
    ):

        @asynccontextmanager
        async def connection() -> AsyncIterator[psycopg.AsyncConnection[tuple[object, ...]]]:
            async with asyncio.timeout(90):
                token = await credential.get_token(
                    "https://ossrdbms-aad.database.windows.net/.default"
                )
                async with await psycopg.AsyncConnection.connect(
                    host=config.postgres_host,
                    dbname=config.postgres_database,
                    user="newsloom_mcp",
                    password=token.token,
                    sslmode="verify-full",
                    sslrootcert="/etc/ssl/certs/ca-certificates.crt",
                    connect_timeout=10,
                    application_name="newsloom-mcp",
                    autocommit=True,
                    options=(
                        "-c statement_timeout=5000 -c idle_in_transaction_session_timeout=10000"
                    ),
                ) as current:
                    yield current

        @asynccontextmanager
        async def repository() -> AsyncIterator[NewsRepository]:
            async with connection() as current, current.transaction():
                await current.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                yield Repository(current, config.embedding_model, config.embedding_version)

        async def ready() -> bool:
            async with connection() as current:
                await current.execute("SELECT id FROM public.news LIMIT 0")
            return True

        transport = ModelClient(
            client, credential, config.model_endpoint, TransportLimits(request_seconds=20)
        )
        verifier = EntraVerifier(client, config.tenant, config.audience)
        telemetry = (
            Telemetry(config.telemetry_routing, str(config.client_id), transport)
            if instrument
            else None
        )
        try:
            yield (
                Services(
                    repository,
                    FoundryQueryEmbedding(transport, config.embedding_deployment),
                    ready,
                    telemetry.record if telemetry else None,
                    telemetry.record_http if telemetry else None,
                ),
                verifier,
            )
        finally:
            if telemetry is not None:
                await asyncio.to_thread(telemetry.close)


@asynccontextmanager
async def application(config: Config) -> AsyncIterator[Starlette]:
    async with resources(config) as (services, verifier):
        host = httpx.URL(config.resource_url).host
        yield create_app(
            services,
            verifier,
            config.resource_url,
            [host, host + ":443"],
            list(config.allowed_origins),
        )
