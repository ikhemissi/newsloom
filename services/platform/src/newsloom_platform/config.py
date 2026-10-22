"""Validated runtime inputs supplied by the selected azd environment."""

import json
from collections.abc import Mapping
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

Workload = Literal["ingestion", "enrichment", "mcp", "migrations"]
RUNTIME_WORKLOADS = ("ingestion", "enrichment", "mcp")


class PlatformFailure(Exception):
    """A safe category, never an upstream response or credential."""


class Identity(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    id: str
    client_id: UUID
    principal_id: UUID


class RuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    identities: dict[str, Identity]
    postgres_host: str
    postgres_database: Literal["newsloom"]
    postgres_admin_name: str
    model_endpoint: str
    enrichment_deployment: str
    embeddings_deployment: str
    screening_deployment: str
    registry_endpoint: str
    model_account_id: str
    applicationinsights_connection_string: str

    @model_validator(mode="after")
    def validate_boundaries(self) -> RuntimeConfig:
        if set(self.identities) != {*RUNTIME_WORKLOADS, "migrations"}:
            raise ValueError("Exactly four workload identities are required.")
        if len({i.principal_id for i in self.identities.values()}) != 4:
            raise ValueError("Workload principals must be distinct.")
        if len({i.client_id for i in self.identities.values()}) != 4:
            raise ValueError("Workload clients must be distinct.")
        if not self.model_endpoint.startswith("https://"):
            raise ValueError("Model access requires HTTPS.")
        if not self.postgres_host or not self.postgres_admin_name:
            raise ValueError("Database connection inputs are required.")
        return self

    @classmethod
    def from_environment(cls, env: Mapping[str, str]) -> RuntimeConfig:
        return cls.model_validate(
            {
                "identities": json.loads(env["WORKLOAD_IDENTITIES"]),
                "postgres_host": env["POSTGRES_HOST"],
                "postgres_database": env["POSTGRES_DATABASE"],
                "postgres_admin_name": env["POSTGRES_ADMIN_NAME"],
                "model_endpoint": env["MODEL_ENDPOINT"],
                "enrichment_deployment": env["ENRICHMENT_DEPLOYMENT"],
                "embeddings_deployment": env["EMBEDDINGS_DEPLOYMENT"],
                "screening_deployment": env["SCREENING_DEPLOYMENT"],
                "registry_endpoint": env["AZURE_CONTAINER_REGISTRY_ENDPOINT"],
                "model_account_id": env["MODEL_ACCOUNT_ID"],
                "applicationinsights_connection_string": env[
                    "APPLICATIONINSIGHTS_CONNECTION_STRING"
                ],
            }
        )


def database_role(workload: str) -> str:
    if workload not in RUNTIME_WORKLOADS:
        raise PlatformFailure("invalid_runtime_workload")
    return f"newsloom_{workload}"


def json_object(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise PlatformFailure("invalid_object_response")
    return dict(value)


def text_field(value: dict[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise PlatformFailure("invalid_text_response")
    return item
