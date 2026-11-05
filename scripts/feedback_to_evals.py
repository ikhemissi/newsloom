"""Turn reviewed feedback exports into eval regression cases (kept out of git).

Usage: uv run --locked python scripts/feedback_to_evals.py feedback.jsonl [--out DIR]

Export from the reviewer page, then add to each line worth keeping:
  "expected": "<what a good briefing or answer should have done>"
Lines without "expected" are skipped. Cases go to .cache/eval-cases/ by default;
scripts/eval.sh validates and reports them.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / ".cache" / "eval-cases"


class Case(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["briefing", "research"]
    source_rating: Literal["up", "down"]
    reader_comment: str | None
    expected: Annotated[str, Field(min_length=1, max_length=2000)]
    briefing_version: str | None = None
    question: str | None = None
    filters: dict[str, object] | None = None
    observed_answer: dict[str, object] | None = None


def convert(line: dict[str, object]) -> Case | None:
    expected = line.get("expected")
    if not isinstance(expected, str) or not expected.strip():
        return None
    kind = line["target_type"]
    snapshot = line.get("snapshot") if isinstance(line.get("snapshot"), dict) else {}
    assert isinstance(snapshot, dict)
    return Case.model_validate(
        {
            "kind": kind,
            "source_rating": line["rating"],
            "reader_comment": line.get("comment"),
            "expected": expected.strip(),
            "briefing_version": line["target_ref"] if kind == "briefing" else None,
            "question": snapshot.get("question") if kind == "research" else None,
            "filters": snapshot.get("filters") if kind == "research" else None,
            "observed_answer": snapshot.get("answer") if kind == "research" else None,
        }
    )


def write_cases(lines: list[dict[str, object]], out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for line in lines:
        case = convert(line)
        if case is None:
            continue
        data = case.model_dump_json(indent=2)
        name = f"{case.kind}-{hashlib.sha256(data.encode()).hexdigest()[:12]}.json"
        (out / name).write_text(data + "\n")
        written.append(out / name)
    return written


def validate(directory: Path) -> dict[str, int]:
    counts = {"briefing": 0, "research": 0}
    for path in sorted(directory.glob("*.json")):
        counts[Case.model_validate_json(path.read_text()).kind] += 1
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export", type=Path, nargs="?")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--validate", action="store_true", help="only validate existing cases")
    arguments = parser.parse_args()
    if not arguments.validate:
        if arguments.export is None:
            parser.error("export file required")
        lines = [
            json.loads(raw) for raw in arguments.export.read_text().splitlines() if raw.strip()
        ]
        written = write_cases(lines, arguments.out)
        print(f"wrote {len(written)} case(s) to {arguments.out}", file=sys.stderr)
    counts = validate(arguments.out) if arguments.out.exists() else {}
    print(json.dumps({"cases": counts}))


if __name__ == "__main__":
    main()
