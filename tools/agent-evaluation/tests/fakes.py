import time
from types import TracebackType
from typing import Self

from azure.core.credentials import AccessToken

TOKEN = "evaluation-test-entra-token"
PROJECT_ENDPOINT = "https://evaluation-test.services.ai.azure.com/api/projects/pilot"


class Credential:
    def __init__(self) -> None:
        self.scopes: list[tuple[str, ...]] = []
        self.closed = False

    async def get_token(self, *scopes: str, **kwargs: object) -> AccessToken:
        self.scopes.append(scopes)
        return AccessToken(TOKEN, int(time.time()) + 3600)

    async def close(self) -> None:
        self.closed = True

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ) -> None:
        await self.close()
