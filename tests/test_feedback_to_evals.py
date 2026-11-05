import importlib.util
import sys
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "feedback_to_evals", ROOT / "scripts" / "feedback_to_evals.py"
)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules["feedback_to_evals"] = module
spec.loader.exec_module(module)

EXPORT = [
    {
        "created_at": "2026-11-05T10:00:00Z",
        "target_type": "briefing",
        "target_ref": str(UUID(int=7)),
        "rating": "down",
        "comment": "Too much AWS",
        "snapshot": None,
        "expected": "Cover at most three items per vendor.",
    },
    {
        "created_at": "2026-11-05T10:01:00Z",
        "target_type": "research",
        "target_ref": "task-1",
        "rating": "down",
        "comment": "Missed the security incident",
        "snapshot": {
            "question": "What changed in LiteLLM?",
            "answer": {"outcome": "supported"},
            "citations": [],
            "filters": {"sources": ["litellm"]},
        },
        "expected": "Mention the compromised release first.",
    },
    {
        "created_at": "2026-11-05T10:02:00Z",
        "target_type": "briefing",
        "target_ref": str(UUID(int=8)),
        "rating": "up",
        "comment": None,
        "snapshot": None,
    },
]


def test_only_reviewed_lines_become_cases(tmp_path: Path) -> None:
    written = module.write_cases(EXPORT, tmp_path)
    assert len(written) == 2
    assert module.validate(tmp_path) == {"briefing": 1, "research": 1}
    research = next(p for p in written if p.name.startswith("research-"))
    case = module.Case.model_validate_json(research.read_text())
    assert case.question == "What changed in LiteLLM?" and case.filters == {"sources": ["litellm"]}
    assert case.briefing_version is None and case.source_rating == "down"


def test_case_files_are_ignored_by_git() -> None:
    assert module.DEFAULT_OUT == ROOT / ".cache" / "eval-cases"
    assert "/.cache/" in (ROOT / ".gitignore").read_text()
