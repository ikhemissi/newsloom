import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from agent_evaluation.policy import (
    PRIVACY_ENVIRONMENT,
    EvaluationFailure,
    configure_privacy,
    verify_environment,
    verify_privacy,
)

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT.parents[1]

IMPORT_PROBE = """
import json, os, sys
attempts = []
def audit(event, args):
    if event in ("socket.connect", "socket.getaddrinfo"):
        attempts.append(event)
        raise RuntimeError("unexpected_network")
sys.addaudithook(audit)
from agent_evaluation.policy import configure_privacy
configure_privacy()
os.chdir(os.environ["HOME"])
from importlib.metadata import version
from deepeval.metrics import FaithfulnessMetric
from deepeval.telemetry import NoopBackend, get_backend
from deepeval.config.settings import get_settings
from azure.ai.projects.aio import AIProjectClient
assert isinstance(get_backend(), NoopBackend)
assert get_settings().CONFIDENT_API_KEY is None
assert "deepeval.plugins.plugin" not in sys.modules
assert "posthog" not in sys.modules
assert not attempts
print(json.dumps({n: version(n) for n in ("deepeval", "azure-ai-projects", "click")}))
"""


def test_real_imports_are_private_and_do_not_load_dotenv(tmp_path: Path) -> None:
    canary = "credential-" + os.urandom(16).hex()
    (tmp_path / ".env").write_text(f"CONFIDENT_API_KEY={canary}\n")
    result = subprocess.run(
        [sys.executable, "-c", IMPORT_PROBE],
        cwd=PROJECT,
        env={
            **os.environ,
            "HOME": str(tmp_path),
            "CONFIDENT_API_KEY": canary,
            "DEEPEVAL_TELEMETRY_OPT_OUT": "0",
            "DEEPEVAL_TELEMETRY_ENABLED": "1",
            "DEEPEVAL_UPDATE_WARNING_OPT_IN": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert lines[:-1] == [
        "Warning: DeepEval is configured for read only environment. Test runs will not be",
        "written to disk.",
    ]
    assert json.loads(lines[-1]) == {
        "deepeval": "4.3.2",
        "azure-ai-projects": "2.9.0",
        "click": "8.3.3",
    }
    assert canary not in result.stdout + result.stderr
    assert {path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*")} == {".env"}


def test_locks_and_environments_are_independent() -> None:
    application = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert "tools/agent-evaluation" in application["tool"]["uv"]["workspace"]["exclude"]
    packages = tomllib.loads((ROOT / "uv.lock").read_text())["package"]
    production = {row["name"]: row["version"] for row in packages}
    evaluation = {
        row["name"]: row["version"]
        for row in tomllib.loads((PROJECT / "uv.lock").read_text())["package"]
    }
    assert "deepeval" not in production
    assert "azure-ai-projects" not in production
    assert production["click"] == "8.5.0"
    assert evaluation["click"] == "8.3.3"
    assert Path(sys.prefix).resolve() == (PROJECT / ".venv").resolve()
    assert {name for name in evaluation if name.startswith("newsloom-")} == {
        "newsloom-agent-evaluation-tools"
    }


@pytest.mark.parametrize("name", tuple(PRIVACY_ENVIRONMENT))
def test_changed_privacy_flags_fail_closed(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(name, "changed")
    with pytest.raises(EvaluationFailure, match="evaluation_privacy_configuration_changed"):
        configure_privacy()


def test_key_injection_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONFIDENT_API_KEY", "injected-test-credential")
    with pytest.raises(EvaluationFailure, match="evaluation_key_credential_present"):
        verify_privacy()


def test_application_environment_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "prefix", str(ROOT / ".venv"))
    with pytest.raises(EvaluationFailure, match="isolated_evaluation_environment_required"):
        verify_environment()


@pytest.mark.parametrize("name", ["PYTHONPATH", "PYTHONHOME"])
def test_environment_import_overrides_are_rejected(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(name, str(ROOT / ".venv"))
    with pytest.raises(EvaluationFailure, match="evaluation_import_path_override_forbidden"):
        verify_environment()
