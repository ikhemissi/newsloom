"""The Web IQ key goes from a hidden prompt to Azure Resource Manager and nowhere else."""

import json

import httpx
import pytest
from newsloom_platform import web_research
from newsloom_platform.config import PlatformFailure

SUBSCRIPTION = "-".join(("00000000", "0000", "0000", "0000", "000000000000"))
PROJECT = (
    f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg-newsloom-test/providers/"
    "Microsoft.CognitiveServices/accounts/ai-newsloom-test/projects/research-newsloom-test"
)
KEY = "WEBIQ-KEY-CANARY-123"


def client(stored: dict[str, object], *, readback: dict[str, object] | None = None) -> httpx.Client:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.path == f"{PROJECT}/connections/webiq"
        if request.method == "PUT":
            stored.update(json.loads(request.content))
            return httpx.Response(201, json={})
        properties = stored["properties"]
        assert isinstance(properties, dict)
        public = {key: value for key, value in properties.items() if key != "credentials"}
        return httpx.Response(200, json=readback or {"properties": public})

    return httpx.Client(transport=httpx.MockTransport(handle))


def test_key_is_written_once_and_never_printed(capsys: pytest.CaptureFixture[str]) -> None:
    stored: dict[str, object] = {}
    web_research.set_connection(
        {"WEB_RESEARCH_PROJECT_ID": PROJECT}, "local", prompt=lambda _: KEY, client=client(stored)
    )
    properties = stored["properties"]
    assert isinstance(properties, dict)
    assert properties["credentials"] == {"keys": {"x-apikey": KEY}}
    assert properties["target"] == "https://api.microsoft.ai/v3/mcp"
    assert properties["isSharedToAll"] is False
    output = capsys.readouterr()
    assert KEY not in output.out + output.err and "webiq_connection" in output.out


@pytest.mark.parametrize(
    ("env", "key", "category"),
    [
        ({}, KEY, "web_research_project_missing"),
        (
            {"WEB_RESEARCH_PROJECT_ID": PROJECT.replace("research-", "eval-")},
            KEY,
            "web_research_project_invalid",
        ),
        ({"WEB_RESEARCH_PROJECT_ID": PROJECT}, " ", "webiq_key_invalid"),
        ({"WEB_RESEARCH_PROJECT_ID": PROJECT}, "two words", "webiq_key_invalid"),
    ],
)
def test_wrong_project_or_key_is_refused_before_any_call(
    env: dict[str, str], key: str, category: str
) -> None:
    def forbidden(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no call expected")

    with pytest.raises(PlatformFailure, match=category):
        web_research.set_connection(
            env,
            "local",
            prompt=lambda _: key,
            client=httpx.Client(transport=httpx.MockTransport(forbidden)),
        )


def test_readback_must_match_the_web_iq_target() -> None:
    with pytest.raises(PlatformFailure, match="webiq_connection_readback_mismatch"):
        web_research.set_connection(
            {"WEB_RESEARCH_PROJECT_ID": PROJECT},
            "local",
            prompt=lambda _: KEY,
            client=client(
                {},
                readback={
                    "properties": {
                        "category": "RemoteTool",
                        "authType": "CustomKeys",
                        "target": "https://elsewhere.test",
                    }
                },
            ),
        )
