"""Smoke-test a locally built static UI with authored public configuration only."""

import argparse
import base64
import json
import re
import subprocess
import time
from uuid import uuid4

import httpx


def command(arguments: list[str], *, timeout: int = 60) -> str:
    result = subprocess.run(arguments, capture_output=True, text=True, timeout=timeout, check=False)
    if result.returncode:
        raise RuntimeError("ui_container_command_failed")
    return result.stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=("docker", "podman"), required=True)
    parser.add_argument("--image", required=True)
    args = parser.parse_args()
    config = {
        "tenantId": str(uuid4()),
        "clientId": str(uuid4()),
        "agentUrl": "https://agent.test/a2a",
        "agentScope": f"api://{uuid4()}/news.agent",
        "mcpUrl": "https://mcp.test/mcp",
        "mcpScope": f"api://{uuid4()}/news.read",
    }
    encoded = base64.b64encode(json.dumps(config).encode()).decode()
    container = command(
        [
            args.engine,
            "run",
            "--rm",
            "-d",
            "-p",
            "127.0.0.1::8080",
            "-e",
            f"UI_CONFIG_BASE64={encoded}",
            "-e",
            "AGENT_ORIGIN=https://agent.test",
            "-e",
            "MCP_ORIGIN=https://mcp.test",
            args.image,
        ]
    )
    try:
        if not re.fullmatch(r"[a-f0-9]{64}", container):
            raise RuntimeError("ui_container_identity_invalid")
        address = command([args.engine, "port", container, "8080/tcp"])
        if not re.fullmatch(r"127\.0\.0\.1:[0-9]+", address):
            raise RuntimeError("ui_container_port_invalid")
        origin = f"http://{address}"
        with httpx.Client(trust_env=False, timeout=5) as client:
            deadline = time.monotonic() + 30
            while True:
                try:
                    response = client.get(origin + "/health/live")
                    if response.status_code == 200:
                        break
                except httpx.TransportError:
                    if time.monotonic() >= deadline:
                        raise RuntimeError("ui_container_unavailable") from None
                if time.monotonic() >= deadline:
                    raise RuntimeError("ui_container_unready")
                time.sleep(0.1)
            config_response = client.get(origin + "/config.json")
            assert config_response.json() == config
            assert config_response.headers["cache-control"] == "no-store"
            html = client.get(origin + "/")
            assert html.status_code == 200
            assert html.headers["cache-control"] == "no-store"
            assert "frame-ancestors 'none'" in html.headers["content-security-policy"]
            assert html.headers["referrer-policy"] == "no-referrer"
            assert html.headers["x-content-type-options"] == "nosniff"
            asset = re.search(r'src="(/assets/[^"]+\.js)"', html.text)
            assert asset is not None
            bundle = client.get(origin + asset[1])
            assert bundle.status_code == 200
            assert "immutable" in bundle.headers["cache-control"]
            assert "/tests/harness" not in bundle.text
            assert client.get(origin + "/auth/callback?code=UI_CONTENT_CANARY").status_code == 200
        assert command([args.engine, "exec", container, "id", "-u"]) == "101"
        assert "UI_CONTENT_CANARY" not in command([args.engine, "logs", container])
        print(
            "UI container: nonroot, configuration, headers, assets, callback and log canary passed"
        )
    finally:
        command([args.engine, "stop", "--time", "5", container])


if __name__ == "__main__":
    main()
