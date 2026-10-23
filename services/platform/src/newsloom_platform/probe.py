"""Synthetic checks executed under one real workload identity at a time."""

import asyncio
import base64
import json
import logging
import re
import time
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import psycopg
from azure.core.credentials_async import AsyncTokenCredential
from pydantic import ValidationError

from newsloom_platform.config import (
    PlatformFailure,
    RuntimeConfig,
    database_role,
    json_object,
    text_field,
)
from newsloom_platform.database import connect
from newsloom_platform.events import event
from newsloom_platform.models import payloads, validate_contract

MODEL_SCOPE = "https://cognitiveservices.azure.com/.default"
CANARY = "NEWSLOOM_CONTENT_CANARY"
CREDENTIAL_CANARY = "NEWSLOOM_CREDENTIAL_CANARY"


def token_claims(token: str) -> dict[str, object]:
    parts = token.split(".")
    if len(parts) != 3:
        raise PlatformFailure("invalid_token_shape")
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    return json_object(json.loads(base64.urlsafe_b64decode(payload)))


async def allowed_request(
    client: httpx.AsyncClient,
    url: str,
    token: str,
    body: object,
    correlation: str,
    *,
    stage: str,
) -> httpx.Response:
    deadline = time.monotonic() + 300
    while True:
        response = await client.post(url, headers={"Authorization": f"Bearer {token}"}, json=body)
        if response.status_code not in [401, 403] or time.monotonic() >= deadline:
            if response.status_code != 200:
                raise PlatformFailure(f"{stage}_http_{response.status_code}")
            return response
        event("permission_retry", "pending", correlation, category=f"http_{response.status_code}")
        await asyncio.sleep(5)


def require_denied(response: httpx.Response, *, stage: str = "authorization") -> None:
    if response.status_code not in [401, 403]:
        raise PlatformFailure(f"denial_not_proven_{stage}_http_{response.status_code}")


def credential_rejected(error: psycopg.OperationalError, user: str) -> bool:
    if error.sqlstate in ["28000", "28P01"]:
        return True
    # libpq connection failures can omit SQLSTATE even for server FATAL responses.
    return bool(
        re.search(
            r'\bFATAL:\s+(?:password authentication failed for user "'
            + re.escape(user)
            + r'"|The access token is (?:invalid|not valid)|JWT token is invalid|Invalid token)'
            r"(?:[.:\s]|$)"
            r"|\bFATAL:[^\r\n]*\baccess token "
            r"(?:(?:has|contains)(?: an?)?|is(?:(?: of| in)(?: an?)?)?) invalid format\b",
            str(error),
            re.IGNORECASE,
        )
    )


async def database_boundary(
    config: RuntimeConfig, credential: AsyncTokenCredential, workload: str
) -> int:
    user = config.postgres_admin_name if workload == "migrations" else database_role(workload)
    async with await connect(config, credential, config.postgres_database, user) as connection:
        row = await (
            await connection.execute(
                "SELECT current_setting('server_version_num')::int, "
                "vector_dims(array_fill(0.0::real, ARRAY[1536])::vector), "
                "pg_has_role(current_user, 'azure_pg_admin', 'member')"
            )
        ).fetchone()
        if (
            row is None
            or not isinstance(row[0], int)
            or not 180000 <= row[0] < 190000
            or row[1] != 1536
            or row[2] != (workload == "migrations")
        ):
            raise PlatformFailure("database_readiness_or_privilege")
        if workload != "migrations":
            row = await (
                await connection.execute(
                    "SELECT has_table_privilege(current_user,'ingestion_queue','INSERT'), "
                    "has_table_privilege(current_user,'quarantine','SELECT'), "
                    "has_table_privilege(current_user,'quarantine','DELETE')"
                )
            ).fetchone()
            expected = workload == "ingestion"
            if row != (expected, expected, False):
                raise PlatformFailure("ingestion_table_grants")
            try:
                async with connection.transaction():
                    await connection.execute(
                        psycopg.sql.SQL("CREATE SCHEMA {}").format(
                            psycopg.sql.Identifier(f"newsloom_probe_{uuid4().hex}")
                        )
                    )
                    raise PlatformFailure("unexpected_schema_creation")
            except psycopg.errors.InsufficientPrivilege:
                pass
            other = "enrichment" if workload != "enrichment" else "mcp"
            try:
                async with connection.transaction():
                    await connection.execute(
                        psycopg.sql.SQL("SET ROLE {}").format(
                            psycopg.sql.Identifier(database_role(other))
                        )
                    )
                    raise PlatformFailure("unexpected_role_inheritance")
            except psycopg.errors.InsufficientPrivilege:
                pass
    try:
        async with await psycopg.AsyncConnection.connect(
            host=config.postgres_host,
            dbname=config.postgres_database,
            user=user,
            password=CREDENTIAL_CANARY,
            sslmode="verify-full",
            sslrootcert="/etc/ssl/certs/ca-certificates.crt",
            connect_timeout=15,
        ):
            raise PlatformFailure("unauthenticated_database_access")
    except psycopg.OperationalError as error:
        if not credential_rejected(error, user):
            raise PlatformFailure("database_denial_not_proven") from None
    return 4 if workload != "migrations" else 2


async def registry_boundary(
    client: httpx.AsyncClient, config: RuntimeConfig, credential: AsyncTokenCredential
) -> None:
    token = await credential.get_token("https://containerregistry.azure.net/.default")
    response = await client.post(
        f"https://{config.registry_endpoint}/oauth2/exchange",
        data={
            "grant_type": "access_token",
            "service": config.registry_endpoint,
            "access_token": token.token,
        },
    )
    if response.status_code != 200:
        raise PlatformFailure(f"registry_exchange_http_{response.status_code}")
    refresh = text_field(json_object(response.json()), "refresh_token")
    response = await client.post(
        f"https://{config.registry_endpoint}/oauth2/token",
        data={
            "grant_type": "refresh_token",
            "service": config.registry_endpoint,
            "scope": "repository:newsloom-platform:pull,push",
            "refresh_token": refresh,
        },
    )
    if response.status_code != 200:
        raise PlatformFailure(f"registry_scope_http_{response.status_code}")
    claims = token_claims(text_field(json_object(response.json()), "access_token"))
    access = claims.get("access")
    if not isinstance(access, list):
        raise PlatformFailure("registry_scope_missing")
    actions: set[str] = set()
    for raw in access:
        item = json_object(raw)
        if item.get("name") == "newsloom-platform" and item.get("type") == "repository":
            values = item.get("actions")
            if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
                raise PlatformFailure("registry_actions_invalid")
            actions.update(values)
    if "pull" not in actions or "push" in actions:
        raise PlatformFailure("registry_pull_push_boundary")


def telemetry_body(
    config: RuntimeConfig, workload: str, correlation: str
) -> tuple[str, list[dict[str, object]]]:
    parts = dict(
        part.split("=", 1)
        for part in config.applicationinsights_connection_string.split(";")
        if part
    )
    endpoint = parts["IngestionEndpoint"].rstrip("/")
    if not endpoint.startswith("https://"):
        raise PlatformFailure("telemetry_https_required")
    return f"{endpoint}/v2.1/track", [
        {
            "name": "Microsoft.ApplicationInsights.Event",
            "time": datetime.now(UTC).isoformat(),
            "iKey": parts["InstrumentationKey"],
            "tags": {"ai.operation.id": correlation, "ai.cloud.role": "newsloom-platform"},
            "data": {
                "baseType": "EventData",
                "baseData": {
                    "ver": 2,
                    "name": "newsloom.platform.probe",
                    "properties": {
                        "correlation_id": correlation,
                        "workload": workload,
                        "outcome": "success",
                    },
                    "measurements": {"checks": 1},
                },
            },
        }
    ]


async def probe(
    config: RuntimeConfig, credential: AsyncTokenCredential, workload: str, correlation: str
) -> int:
    model_token = await credential.get_token(MODEL_SCOPE)
    if token_claims(model_token.token).get("oid") != str(config.identities[workload].principal_id):
        raise PlatformFailure("unexpected_execution_identity")
    checks = await database_boundary(config, credential, workload)
    allowed = {
        "ingestion": {"screening"},
        "enrichment": {"enrichment", "embeddings"},
        "mcp": {"embeddings"},
        "migrations": set(),
    }[workload]
    async with httpx.AsyncClient(timeout=30) as client:
        for kind, (path, body) in payloads(
            config.enrichment_deployment, config.embeddings_deployment, config.screening_deployment
        ).items():
            url = config.model_endpoint.rstrip("/") + path
            deployment = text_field(body, "model")
            if kind in allowed:
                response = await allowed_request(
                    client, url, model_token.token, body, correlation, stage=deployment
                )
                try:
                    validate_contract(kind, response.json())
                except ValidationError, json.JSONDecodeError:
                    raise PlatformFailure(f"{deployment}_contract_invalid") from None
            else:
                require_denied(
                    await client.post(
                        url, headers={"Authorization": f"Bearer {model_token.token}"}, json=body
                    ),
                    stage=deployment,
                )
            checks += 1
        require_denied(
            await client.post(
                config.model_endpoint.rstrip("/") + "/openai/v1/responses",
                headers={"Authorization": f"Bearer {model_token.token}"},
                json={
                    "model": config.enrichment_deployment,
                    "input": CANARY,
                    "max_output_tokens": 16,
                },
            )
        )
        management = await credential.get_token("https://management.azure.com/.default")
        require_denied(
            await client.post(
                f"https://management.azure.com{config.model_account_id}/listKeys?api-version=2025-06-01",
                headers={"Authorization": f"Bearer {management.token}"},
            )
        )
        await registry_boundary(client, config, credential)
        url, batch = telemetry_body(config, workload, correlation)
        telemetry = await credential.get_token("https://monitor.azure.com/.default")
        if workload == "migrations":
            require_denied(
                await client.post(
                    url, headers={"Authorization": f"Bearer {telemetry.token}"}, json=batch
                )
            )
        else:
            result = json_object(
                (
                    await allowed_request(
                        client, url, telemetry.token, batch, correlation, stage="telemetry"
                    )
                ).json()
            )
            if any(
                type(result.get(key)) is not int or result[key] != 1
                for key in ["itemsAccepted", "itemsReceived"]
            ):
                raise PlatformFailure("telemetry_not_accepted")
        require_denied(await client.post(url, json=batch))
    logging.getLogger("httpx").warning("%s %s %s", CANARY, CREDENTIAL_CANARY, correlation)
    return checks + 5
