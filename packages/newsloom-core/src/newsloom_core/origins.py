"""Canonical exact HTTPS browser-origin configuration shared by deployment and runtime."""

import re
from collections.abc import Mapping, Sequence

import httpx


def normalize_origins(values: Sequence[str]) -> tuple[str, ...]:
    for value in values:
        if not re.fullmatch(r"https://[a-z0-9]+([.-][a-z0-9]+)*(:[0-9]+)?", value):
            raise ValueError("invalid_allowed_origin")
        url = httpx.URL(value)
        if str(url).removesuffix("/") != value or (
            url.port is not None and not 1 <= url.port <= 65535
        ):
            raise ValueError("noncanonical_allowed_origin")
    return tuple(sorted(set(values)))


class BrowserPolicy:
    def __init__(
        self,
        origins: Sequence[str],
        methods: Mapping[str, str],
        headers: frozenset[str],
    ) -> None:
        self.origins = normalize_origins(origins)
        self.methods = dict(methods)
        self.headers = headers

    def origin(self, values: Sequence[str]) -> str:
        if len(values) != 1 or values[0] not in self.origins:
            raise ValueError("origin_denied")
        return values[0]

    def accepts_preflight(
        self,
        path: str,
        methods: Sequence[str],
        headers: Sequence[str],
    ) -> bool:
        fields = [field.strip().lower() for field in headers[0].split(",")] if headers else []
        return (
            len(methods) == 1
            and methods[0] == self.methods.get(path)
            and len(headers) <= 1
            and all(field in self.headers for field in fields)
        )

    def preflight_headers(self) -> dict[str, str]:
        return {
            "Access-Control-Allow-Methods": ", ".join(sorted(set(self.methods.values()))),
            "Access-Control-Allow-Headers": ", ".join(sorted(self.headers)),
            "Access-Control-Max-Age": "300",
            "Vary": "Origin, Access-Control-Request-Method, Access-Control-Request-Headers",
        }
