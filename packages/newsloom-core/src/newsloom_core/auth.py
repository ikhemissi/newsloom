"""Framework-neutral, single-tenant verification using only configured trusted keys."""

import asyncio
import json
import time
from typing import Annotated
from uuid import UUID

import httpx
import jwt
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class Claims(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)
    iss: str
    aud: str
    tid: UUID
    sub: Annotated[str, Field(min_length=1, max_length=256)]
    azp: UUID
    exp: Annotated[int, Field(strict=True)]
    nbf: Annotated[int, Field(strict=True)]
    ver: str
    scp: Annotated[str, Field(max_length=2048)] = ""


class TrustedKeysFailure(Exception):
    """An application-owned trusted-key availability category."""


class EntraTokenVerifier[ClaimT: Claims]:
    def __init__(
        self,
        client: httpx.AsyncClient,
        tenant: UUID,
        audience: UUID,
        claims_type: type[ClaimT],
    ) -> None:
        self.client = client
        self.tenant, self.audience = tenant, str(audience)
        self.claims_type = claims_type
        self.issuer = f"https://login.microsoftonline.com/{tenant}/v2.0"
        self.jwks_url = f"https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys"
        self.keys: dict[str, jwt.PyJWK] = {}
        self.refreshed_at = 0.0
        self.attempted_at = 0.0
        self.lock = asyncio.Lock()

    async def refresh(self) -> None:
        async with self.lock:
            if self.attempted_at and time.monotonic() - self.attempted_at < 60:
                return
            self.attempted_at = time.monotonic()
            try:
                async with (
                    asyncio.timeout(5),
                    self.client.stream("GET", self.jwks_url, timeout=5) as response,
                ):
                    if response.status_code != 200:
                        raise TrustedKeysFailure("trusted_keys_unavailable")
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        data.extend(chunk)
                        if len(data) > 128 * 1024:
                            raise TrustedKeysFailure("trusted_keys_response_limit")
                value: object = json.loads(data)
                if not isinstance(value, dict) or not isinstance(value.get("keys"), list):
                    raise TrustedKeysFailure("invalid_trusted_keys")
                keys: dict[str, jwt.PyJWK] = {}
                for item in value["keys"]:
                    if not isinstance(item, dict) or item.get("kty") != "RSA":
                        continue
                    if not isinstance(item.get("kid"), str) or item.get("use") not in (None, "sig"):
                        continue
                    key = jwt.PyJWK.from_dict(item, algorithm="RS256")
                    keys[item["kid"]] = key
                if not keys:
                    raise TrustedKeysFailure("invalid_trusted_keys")
            except httpx.HTTPError, TimeoutError, ValueError, jwt.PyJWTError:
                raise TrustedKeysFailure("trusted_keys_unavailable") from None
            self.keys = keys
            self.refreshed_at = time.monotonic()

    async def verify_claims(self, token: str) -> ClaimT | None:
        if len(token) > 16 * 1024:
            return None
        try:
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            if (
                header.get("alg") != "RS256"
                or not isinstance(kid, str)
                or not 1 <= len(kid) <= 256
                or any(key in header for key in ("jku", "x5u", "jwk"))
            ):
                return None
            if kid not in self.keys or time.monotonic() - self.refreshed_at > 3600:
                await self.refresh()
            key = self.keys.get(kid)
            if key is None or time.monotonic() - self.refreshed_at > 3600:
                return None
            decoded = jwt.decode(
                token,
                key.key,
                algorithms=["RS256"],
                audience=self.audience,
                issuer=self.issuer,
                options={"require": ["exp", "nbf", "iss", "aud", "sub", "tid", "azp", "ver"]},
            )
            claims = self.claims_type.model_validate(decoded)
            if claims.tid != self.tenant or claims.ver != "2.0":
                return None
            return claims
        except jwt.PyJWTError, ValidationError, ValueError:
            return None
