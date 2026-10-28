import asyncio
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import httpx2
import pytest
from openai import OpenAIError

CONTENT = "The authored evidence and synthetic explanation privacy canary."
SECRET = "synthetic-credential-and-provider-error-canary"
PROJECT = Path(__file__).resolve().parents[1]

PROBE = """
import os, sys, threading
from pathlib import Path
home = Path(os.environ["HOME"]).resolve()
network = []
writes = []
relative = threading.local()
original_open = os.open
def observed_open(path, flags, mode=0o777, *, dir_fd=None):
    relative.directory = (
        Path(os.readlink(f"/proc/self/fd/{dir_fd}")) if dir_fd is not None else None
    )
    try:
        return original_open(path, flags, mode, dir_fd=dir_fd)
    finally:
        relative.directory = None
os.open = observed_open
def audit(event, args):
    if event == "subprocess.Popen" and args[1] == ["uname", "-p"]:
        return
    if event in ("socket.connect", "socket.getaddrinfo", "subprocess.Popen"):
        network.append(event)
        raise RuntimeError("unexpected_network_or_process")
    if event == "open" and isinstance(args[0], (str, bytes)):
        flags = args[2]
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC):
            target = Path(os.fsdecode(args[0]))
            directory = getattr(relative, "directory", None)
            if not target.is_absolute() and directory is not None:
                target = directory / target
            target = target.resolve()
            if target == Path(os.devnull):
                return
            writes.append(str(target))
            if not target.is_relative_to(home):
                raise RuntimeError("unexpected_filesystem_write")
sys.addaudithook(audit)
from agent_evaluation.policy import configure_privacy
configure_privacy()
sys.path.insert(0, "tests")
from test_privacy import exercise
exercise(home, sys.argv[1])
assert not network
assert writes
print('{"outcome":"privacy_verified"}')
"""


def _boundary(error: BaseException, monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_evaluation import __main__, runner

    async def fail(*args: object, **kwargs: object) -> object:
        raise error

    monkeypatch.setattr(runner, "score", fail)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "agent_evaluation",
            "score",
            "--manifest",
            "/unused",
            "--approved-sha256",
            "a" * 64,
            "--output",
            "/unused",
        ],
    )
    assert __main__.main() == (130 if isinstance(error, asyncio.CancelledError) else 1)


def exercise(home: Path, mode: str) -> None:
    import logging

    from test_cleanup import prepare
    from test_publication import setup
    from test_runner import test_score_runs_real_metric_and_sdk_with_private_durable_artifacts

    from agent_evaluation import __main__
    from agent_evaluation.policy import verify_privacy

    root = home / "owned"
    root.mkdir(mode=0o700)
    logging.getLogger("privacy-probe").critical(CONTENT + SECRET)
    with pytest.MonkeyPatch.context() as monkeypatch:
        if mode.startswith("score"):
            import test_runner
            from chat_fakes import scripted_chat

            old = scripted_chat

            def chat(
                request: httpx2.Request,
                *,
                unsupported: bool = False,
                snapshot: str,
            ) -> httpx2.Response:
                if mode == "score_failure":
                    return httpx2.Response(500, json={"error": {"message": SECRET + CONTENT}})
                if mode == "score_cancel":
                    raise asyncio.CancelledError(SECRET + CONTENT)
                response = old(request, unsupported=unsupported, snapshot=snapshot)
                body = response.json()
                content = json.loads(body["choices"][0]["message"]["content"])
                if "reason" in content:
                    body["choices"][0]["message"]["content"] = json.dumps({"reason": CONTENT})
                return httpx2.Response(200, json=body)

            monkeypatch.setattr(test_runner, "scripted_chat", chat)
            caught: BaseException | None = None
            try:
                asyncio.run(
                    test_score_runs_real_metric_and_sdk_with_private_durable_artifacts(
                        root, monkeypatch
                    )
                )
            except (OpenAIError, asyncio.CancelledError) as error:
                caught = error
            if mode != "score_success":
                assert caught is not None
                budget = json.loads((root / "evaluation/budget.json").read_bytes())["budget"]
                assert budget["attempts"] == budget["usage_unknown"] == 1
                assert budget["admission_halted"]
                _boundary(caught, monkeypatch)
            else:
                assert caught is None
                assert CONTENT in (root / "evaluation/results.json").read_text()
        elif mode.startswith("publish"):
            path, digest, service = asyncio.run(setup(root, monkeypatch))
            old_respond = service.respond

            def respond(request: httpx2.Request) -> httpx2.Response:
                if mode == "publish_failure":
                    raise httpx2.ReadTimeout(SECRET + CONTENT, request=request)
                if mode == "publish_cancel":
                    raise asyncio.CancelledError(SECRET + CONTENT)
                return old_respond(request)

            monkeypatch.setattr(service, "respond", respond)
            monkeypatch.setattr(
                sys,
                "argv",
                [
                    "agent_evaluation",
                    "publish",
                    "--directory",
                    str(path),
                    "--approved-sha256",
                    digest,
                ],
            )
            expected = 0 if mode == "publish_success" else 130 if mode.endswith("cancel") else 1
            assert __main__.main() == expected
            state = json.loads((path / "publication-state.json").read_bytes())
            if expected:
                assert state["verification"] == "failed"
                assert state["mutations"] == ["catalog"]
        else:
            path, manifest, digest, service_delete = asyncio.run(prepare(root, monkeypatch))
            old_delete = service_delete.respond

            def remove(request: httpx2.Request) -> httpx2.Response:
                if request.method == "DELETE":
                    if mode == "cleanup_failure":
                        raise httpx2.ReadTimeout(SECRET + CONTENT, request=request)
                    if mode == "cleanup_cancel":
                        raise asyncio.CancelledError(SECRET + CONTENT)
                return old_delete(request)

            def inner(**kwargs: object) -> httpx2.MockTransport:
                return httpx2.MockTransport(remove)

            monkeypatch.setattr(httpx2, "AsyncHTTPTransport", inner)
            monkeypatch.setattr(
                sys,
                "argv",
                [
                    "agent_evaluation",
                    "cleanup",
                    "--directory",
                    str(path),
                    "--manifest",
                    str(manifest),
                    "--approved-sha256",
                    digest,
                    "--delete",
                ],
            )
            expected = 0 if mode == "cleanup_success" else 130 if mode.endswith("cancel") else 1
            assert __main__.main() == expected
            state = json.loads((path / "cleanup-state.json").read_bytes())
            if expected:
                assert state["outcome"] == "failed"
                assert state["attempted"] == ["run"]
        verify_privacy()
    allowed = {
        "approval.json",
        "cleanup-approval.json",
        "evaluation/approval.json",
        "evaluation/budget.json",
        "evaluation/partial-results.json",
        "evaluation/results.json",
        "pilot/approval.json",
        "pilot/results.json",
        "pilot/publication-state.json",
        "pilot/publication.json",
        "pilot/publication.lock",
        "pilot/cleanup-state.json",
        "pilot/cleanup.json",
    }
    for path in home.rglob("*"):
        relative = path.relative_to(home).as_posix()
        if path.is_dir():
            assert relative in {"owned", "owned/registry", "owned/evaluation", "owned/pilot"}
            continue
        if relative == ".env":
            continue
        name = path.relative_to(root).as_posix()
        assert name in allowed or re.fullmatch(r"registry/[a-f0-9]{64}\.json", name)
        data = path.read_bytes()
        assert SECRET.encode() not in data
        assert b"evaluation-test-entra-token" not in data
        if CONTENT.encode() in data:
            assert name in {"evaluation/results.json", "evaluation/partial-results.json"}
        if path.parent.name in {"evaluation", "pilot", "registry"}:
            assert path.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    "mode",
    [
        "score_success",
        "score_failure",
        "score_cancel",
        "publish_success",
        "publish_failure",
        "publish_cancel",
        "cleanup_success",
        "cleanup_failure",
        "cleanup_cancel",
    ],
)
def test_fresh_process_canaries_and_filesystem_inventory(mode: str, tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(f"CONFIDENT_API_KEY={SECRET}\n")
    result = subprocess.run(
        [sys.executable, "-c", PROBE, mode],
        cwd=PROJECT,
        env={
            **os.environ,
            "HOME": str(tmp_path),
            "TMPDIR": str(tmp_path),
            "XDG_CACHE_HOME": str(tmp_path / "cache"),
            "CONFIDENT_API_KEY": SECRET,
            "OPENAI_API_KEY": SECRET,
            "DEEPEVAL_TELEMETRY_ENABLED": "1",
            "DEEPEVAL_TELEMETRY_OPT_OUT": "0",
            "ENABLE_DEEPEVAL_CACHE": "1",
            "CONFIDENT_TRACE_SAMPLE_RATE": "1",
            "OTEL_SDK_DISABLED": "false",
            "OTEL_TRACES_EXPORTER": "otlp",
            "OPENAI_LOG": "debug",
            "AZURE_LOG_LEVEL": "debug",
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert SECRET not in result.stdout + result.stderr
    assert CONTENT not in result.stdout + result.stderr
    assert "evaluation-test-entra-token" not in result.stdout + result.stderr
    assert result.stdout.splitlines()[-1] == '{"outcome":"privacy_verified"}'
    for line in result.stdout.splitlines()[:-1]:
        if line.startswith("{"):
            assert set(json.loads(line)) <= {
                "outcome",
                "category",
                "cases",
                "ui_verified",
                "model_calls",
                "assets",
            }
        else:
            assert line in {
                "Warning: DeepEval is configured for read only environment. Test runs will not be",
                "written to disk.",
            }
