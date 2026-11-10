"""Web IQ connection held by the web-research Foundry project.

The key is read from a hidden prompt and sent once to Azure Resource Manager from
memory; it is never written to disk, the azd environment, Terraform state or logs.
"""

import getpass
import re
from collections.abc import Callable

import httpx
from azure.identity import AzureCliCredential

from newsloom_platform.config import PlatformFailure, json_object
from newsloom_platform.events import event

API_VERSION = "2025-06-01"
CONNECTION = "webiq"
TARGET = "https://api.microsoft.ai/v3/mcp"
KEY_HEADER = "x-apikey"
PROJECT = re.compile(
    r"^/subscriptions/[0-9a-f-]{36}/resourceGroups/[\w.-]+/providers/"
    r"Microsoft\.CognitiveServices/accounts/[\w-]+/projects/research-newsloom-[\w-]+$"
)


def connection_url(project_id: str) -> str:
    if not PROJECT.fullmatch(project_id):
        raise PlatformFailure("web_research_project_invalid")
    return (
        f"https://management.azure.com{project_id}/connections/{CONNECTION}"
        f"?api-version={API_VERSION}"
    )


def body(key: str) -> dict[str, object]:
    return {
        "properties": {
            "category": "RemoteTool",
            "authType": "CustomKeys",
            "target": TARGET,
            "isSharedToAll": False,
            "credentials": {"keys": {KEY_HEADER: key}},
            "metadata": {"ApiType": "External"},
        }
    }


def verify(document: object) -> None:
    properties = json_object(json_object(document).get("properties"))
    if (
        properties.get("category") != "RemoteTool"
        or properties.get("authType") != "CustomKeys"
        or properties.get("target") != TARGET
    ):
        raise PlatformFailure("webiq_connection_readback_mismatch")


def set_connection(
    env: dict[str, str],
    correlation: str,
    *,
    prompt: Callable[[str], str] = getpass.getpass,
    client: httpx.Client | None = None,
) -> None:
    project = env.get("WEB_RESEARCH_PROJECT_ID", "")
    if not project:
        raise PlatformFailure("web_research_project_missing")
    url = connection_url(project)
    key = prompt("Web IQ API key (input hidden): ").strip()
    if not key or len(key) > 512 or any(char.isspace() for char in key):
        raise PlatformFailure("webiq_key_invalid")
    owned = client is None
    http = client or httpx.Client(timeout=60, trust_env=False)
    try:
        if owned:
            token = AzureCliCredential().get_token("https://management.azure.com/.default").token
            http.headers["Authorization"] = f"Bearer {token}"
        response = http.put(url, json=body(key))
        del key
        if response.status_code not in (200, 201):
            raise PlatformFailure(f"webiq_connection_write_{response.status_code}")
        readback = http.get(url)
        if readback.status_code != 200:
            raise PlatformFailure(f"webiq_connection_read_{readback.status_code}")
        verify(readback.json())
    finally:
        if owned:
            http.close()
    event("webiq_connection", "set", correlation, category=CONNECTION)
