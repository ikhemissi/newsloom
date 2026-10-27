"""Single-tenant access-token verification; only trusted keys may establish identity."""

from uuid import UUID

import httpx
from mcp.server.auth.provider import AccessToken, TokenVerifier
from newsloom_core.auth import Claims as Claims
from newsloom_core.auth import EntraTokenVerifier, TrustedKeysFailure
from newsloom_core.diagnostics import event


class EntraVerifier(EntraTokenVerifier[Claims], TokenVerifier):
    def __init__(self, client: httpx.AsyncClient, tenant: UUID, audience: UUID) -> None:
        super().__init__(client, tenant, audience, Claims)
        self.scope = f"api://{audience}/news.read"

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            claims = await self.verify_claims(token)
            if claims is None:
                return None
            scopes = [self.scope] if "news.read" in claims.scp.split() else []
            return AccessToken(
                token=token,
                client_id=str(claims.azp),
                subject=claims.sub,
                scopes=scopes,
                expires_at=claims.exp,
                resource=claims.aud,
            )
        except TrustedKeysFailure as error:
            event("mcp_auth", "", outcome="unavailable", category=str(error))
            return None
        except ValueError:
            return None
