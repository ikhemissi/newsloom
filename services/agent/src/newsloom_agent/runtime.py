"""Managed-identity-only MCP, fixed chat and authenticated telemetry resources."""

import asyncio
import os
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from uuid import UUID

import httpx
from azure.identity.aio import ManagedIdentityCredential
from pydantic import ConfigDict, Field, field_validator, model_validator
from starlette.types import ASGIApp

from newsloom_agent.app import create_app
from newsloom_agent.auth import AgentVerifier
from newsloom_agent.delegation import DelegatedMcp, DelegationConfig
from newsloom_agent.generation import FoundryGenerator, GenerationConfig
from newsloom_agent.telemetry import Telemetry


class Config(DelegationConfig):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    identity_client_id: UUID
    resource_url: str
    generation: GenerationConfig
    telemetry_routing: str = Field(min_length=1, repr=False)
    allowed_origins: tuple[str, ...] = ()

    @field_validator("resource_url")
    @classmethod
    def https_interface(cls, value: str) -> str:
        url = httpx.URL(value)
        if (
            url.scheme != "https"
            or not url.host
            or url.userinfo
            or url.query
            or url.fragment
            or url.port not in (None, 443)
            or url.path != "/a2a"
        ):
            raise ValueError("invalid_agent_resource_url")
        return value

    @field_validator("allowed_origins")
    @classmethod
    def explicit_origins(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for value in values:
            url = httpx.URL(value)
            if (
                url.scheme != "https"
                or not url.host
                or "*" in value
                or url.userinfo
                or url.query
                or url.fragment
                or url.path not in ("", "/")
                or value.endswith("/")
            ):
                raise ValueError("invalid_agent_allowed_origin")
        return values

    @model_validator(mode="after")
    def separate_identity(self) -> Config:
        if self.identity_client_id in (self.agent_client_id, self.mcp_audience):
            raise ValueError("separate_workload_and_api_identities_required")
        return self

    @classmethod
    def from_environment(cls, env: Mapping[str, str]) -> Config:
        return cls.model_validate(
            {
                "tenant": env["AGENT_TENANT_ID"],
                "agent_client_id": env["AGENT_API_CLIENT_ID"],
                "identity_client_id": env["AZURE_CLIENT_ID"],
                "resource_url": env["AGENT_RESOURCE_URL"],
                "mcp_audience": env["MCP_API_CLIENT_ID"],
                "mcp_url": env["MCP_RESOURCE_URL"],
                "generation": {
                    "endpoint": env["MODEL_ENDPOINT"],
                    "deployment": env["AGENT_CHAT_DEPLOYMENT"],
                },
                "telemetry_routing": env["APPLICATIONINSIGHTS_CONNECTION_STRING"],
                "allowed_origins": tuple(
                    filter(None, env.get("AGENT_ALLOWED_ORIGINS", "").split(","))
                ),
            }
        )


@asynccontextmanager
async def application(config: Config) -> AsyncIterator[ASGIApp]:
    async with (
        ManagedIdentityCredential(client_id=str(config.identity_client_id)) as credential,
        httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=5) as client,
    ):
        telemetry = Telemetry(config.telemetry_routing, str(config.identity_client_id))
        try:
            yield create_app(
                DelegatedMcp(config, credential, client),
                AgentVerifier(client, config.tenant, config.agent_client_id),
                public_url=config.resource_url,
                allowed_origins=config.allowed_origins,
                generator=FoundryGenerator(config.generation, credential),
                observer=telemetry,
            )
        finally:
            await asyncio.to_thread(telemetry.close)


def environment_config() -> Config:
    return Config.from_environment(os.environ)
