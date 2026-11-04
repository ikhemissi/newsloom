import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("check_plan", ROOT / "scripts" / "check_plan.py")
assert spec and spec.loader
check_plan = importlib.util.module_from_spec(spec)
sys.modules["check_plan"] = check_plan
spec.loader.exec_module(check_plan)


def plan(*files: str) -> dict[str, object]:
    result: dict[str, object] = check_plan.plan(list(files))
    return result


def test_docs_only_change_runs_no_suites() -> None:
    result = plan("docs/briefing.md", "README.md")
    assert result == {
        "changed": 2,
        "everything": False,
        "evaluation": False,
        "python_tests": [],
        "web": False,
        "terraform": [],
    }


def test_service_change_selects_tests_that_import_it() -> None:
    tests = plan("services/briefing/src/newsloom_briefing/generation.py")["python_tests"]
    assert isinstance(tests, list)
    assert "tests/test_briefing.py" in tests and "tests/test_briefing_golden.py" in tests
    assert "tests/test_agent_serving.py" not in tests


def test_core_module_change_follows_service_imports_and_web_fixture() -> None:
    result = plan("packages/newsloom-core/src/newsloom_core/briefing.py")
    tests = result["python_tests"]
    assert isinstance(tests, list)
    assert "tests/test_briefing_api.py" in tests and "tests/test_briefing.py" in tests
    assert "tests/test_ingestion_feeds.py" not in tests
    assert result["web"] is True


def test_manifest_or_unknown_change_selects_everything() -> None:
    every = sorted(str(p.relative_to(ROOT)) for p in (ROOT / "tests").glob("test_*.py"))
    for path in ("uv.lock", "Makefile"):
        result = plan(path)
        assert result["everything"] is True and result["evaluation"] is True
        assert result["python_tests"] == every
        assert len(result["terraform"]) >= 15  # type: ignore[arg-type]


def test_terraform_change_selects_only_its_layer() -> None:
    assert plan("infra/briefing/main.tf")["terraform"] == ["infra/briefing"]
    assert plan("infra/tests/main.tftest.hcl")["terraform"] == ["infra"]
    assert plan("services/web/src/App.tsx")["web"] is True


def test_evaluation_tooling_change_selects_evaluation_only() -> None:
    result = plan("tools/agent-evaluation/agent_evaluation/cleanup.py")
    assert result["evaluation"] is True and result["web"] is False
    assert result["python_tests"] in ([], ["tests/test_check_plan.py"])
