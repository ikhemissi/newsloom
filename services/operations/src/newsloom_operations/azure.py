"""Azure Resource Manager calls for the server operating window and tag repair."""

import asyncio
import time
from collections.abc import Awaitable, Callable

import httpx

ARM = "https://management.azure.com"
SERVER_API = "2024-08-01"
RESOURCE_API = "2021-04-01"
STORAGE_API = "2023-05-01"
GOVERNANCE_TAGS = {"CostControl": "Ignore", "SecurityControl": "Ignore"}
STABLE = {"Ready", "Stopped"}

Token = Callable[[], Awaitable[str]]


class Failure(Exception):
    """Content-free failure category."""


class Manager:
    def __init__(self, client: httpx.AsyncClient, token: Token, *, poll: float = 15) -> None:
        self.client = client
        self.token = token
        self.poll = poll

    async def request(self, method: str, url: str, body: object = None) -> httpx.Response:
        headers = {"Authorization": f"Bearer {await self.token()}"}
        response = await self.client.request(method, url, json=body, headers=headers)
        if response.status_code >= 400:
            raise Failure(f"arm_{method.lower()}_{response.status_code}")
        return response

    async def state(self, server: str) -> str:
        response = await self.request("GET", f"{ARM}{server}?api-version={SERVER_API}")
        state = response.json().get("properties", {}).get("state")
        if not isinstance(state, str):
            raise Failure("arm_invalid_server_state")
        return state

    async def power(self, server: str, target: str, within: float = 1800) -> bool:
        """Bring the server to Ready or Stopped; returns whether an action was sent."""
        action = {"Ready": "start", "Stopped": "stop"}[target]
        deadline = time.monotonic() + within
        sent = False
        while time.monotonic() < deadline:
            state = await self.state(server)
            if state == target:
                return sent
            if state in STABLE and not sent:
                await self.request("POST", f"{ARM}{server}/{action}?api-version={SERVER_API}")
                sent = True
            await asyncio.sleep(self.poll)
        raise Failure(f"database_{action}_timeout")

    async def restore_tags(self, group: str) -> dict[str, int]:
        targets: list[str] = []
        response = await self.request("GET", f"{ARM}{group}?api-version={RESOURCE_API}")
        if not GOVERNANCE_TAGS.items() <= (response.json().get("tags") or {}).items():
            targets.append(group)
        url: str | None = f"{ARM}{group}/resources?api-version={RESOURCE_API}"
        resources = 0
        while url:
            page = (await self.request("GET", url)).json()
            for row in page.get("value", []):
                resources += 1
                if not GOVERNANCE_TAGS.items() <= (row.get("tags") or {}).items():
                    targets.append(str(row["id"]))
            url = page.get("nextLink")
        failed = 0
        for target in targets:
            try:
                await self.request(
                    "PATCH",
                    f"{ARM}{target}/providers/Microsoft.Resources/tags/default"
                    f"?api-version={RESOURCE_API}",
                    {"operation": "Merge", "properties": {"tags": GOVERNANCE_TAGS}},
                )
            except Failure:
                failed += 1
        return {"resources": resources, "tagged": len(targets) - failed, "failed": failed}

    async def restore_public_access(self, account: str) -> bool:
        """Re-enable public network access on the Terraform state account; True if changed."""
        url = f"{ARM}{account}?api-version={STORAGE_API}"
        current = (await self.request("GET", url)).json().get("properties", {})
        if current.get("publicNetworkAccess") == "Enabled":
            return False
        await self.request("PATCH", url, {"properties": {"publicNetworkAccess": "Enabled"}})
        return True
