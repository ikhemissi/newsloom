"""Replay a recorded synthetic week through the real pipeline and preview renderer.

The recording reproduces model mistakes seen in production: source IDs in prose,
quoted facts, duplicate paragraphs, invented numbers, one vendor dominating,
vendor showcases posing as case studies and unsupported case-study services.
"""

import asyncio
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from newsloom_briefing.generation import synthesize
from newsloom_briefing.preview import Replay, load_evidence, load_recording, render

# Fixtures use <id:n> placeholders: committed files must not contain GUID-like values.
IDS = re.compile(r"<id:(\d+)>")


def materialize(source: Path, target: Path) -> Path:
    target.write_text(IDS.sub(lambda m: str(UUID(int=int(m.group(1)))), source.read_text()))
    return target


GOLDEN = Path(__file__).parent / "fixtures" / "briefing-golden"
CUTOFF = datetime(2026, 11, 4, 5, tzinfo=UTC)


def test_golden_week_replay_produces_a_clean_architect_briefing(tmp_path: Path) -> None:
    evidence = load_evidence([materialize(GOLDEN / "evidence.json", tmp_path / "e.json")], CUTOFF)
    recording = load_recording(materialize(GOLDEN / "recording.jsonl", tmp_path / "r.jsonl"))
    generator = Replay(recording, live=None)
    artifact = asyncio.run(synthesize(generator, evidence, CUTOFF, time.monotonic() + 60))
    text = render(artifact)
    paragraphs = [p.text for s in artifact.sections for p in s.paragraphs]
    assert artifact.evidence_count == 8 and artifact.editorial_policy == "architect-v1"
    assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-", text.split("**Sources**")[0])
    assert len(paragraphs) == len(set(paragraphs))
    assert "99%" not in text
    assert paragraphs[0].startswith("Libcore published a malicious libcore==1.9.0")
    assert artifact.sections[-1].heading == "Customer case studies"
    (case,) = artifact.sections[-1].paragraphs
    assert case.text == (
        "Contoso: automated invoice exceptions with human approval "
        "(Acme Cloud Agents, Acme Cloud Storage)."
    )
    assert "Acme Vision" not in text and "funding" not in text.casefold()
    words = sum(len(p.split()) for p in paragraphs)
    assert artifact.tldr is not None and words + len(artifact.tldr.text.split()) <= 1000
