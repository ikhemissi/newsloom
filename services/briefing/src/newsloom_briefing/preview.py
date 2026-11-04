"""Local, non-publishing briefing preview against exported stored news.

Runs the production generation pipeline with the developer's Azure CLI identity,
writes the rendered result under a gitignored directory and never touches the
database. Recorded model stages can be replayed to iterate on later stages for
seconds and cents instead of rerunning every model call.
"""

import argparse
import asyncio
import json
import os
import sys
import time
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import TypeVar
from uuid import UUID

import httpx
from newsloom_core.briefing import Briefing, cutoff_at
from newsloom_core.model_transport import ModelClient, TransportLimits
from pydantic import BaseModel

from newsloom_briefing.generation import FoundryGenerator, Generator, synthesize
from newsloom_briefing.repository import Evidence, Repository

T = TypeVar("T", bound=BaseModel)
EVIDENCE_FIELDS = set(Evidence.model_fields)


class Ledger(Repository):
    """In-memory accounting; a preview never writes to the database."""

    def __init__(self) -> None:
        self.stages: dict[int, str] = {}
        self.calls: list[tuple[str, int, int, Decimal]] = []

    async def intent(self, cutoff: datetime, ordinal: int, stage: str, price_basis: str) -> None:
        self.stages[ordinal] = stage

    async def usage(
        self,
        cutoff: datetime,
        ordinal: int,
        state: str,
        input_tokens: int | None,
        output_tokens: int | None,
        elapsed: float,
        cost: Decimal | None,
    ) -> None:
        self.calls.append(
            (self.stages[ordinal], input_tokens or 0, output_tokens or 0, cost or Decimal(0))
        )
        print(f"call {len(self.calls)}: {self.stages[ordinal]} {state}", file=sys.stderr)


class RoundRobin:
    """Alternate between same-model deployments, each keeping its own pacing."""

    def __init__(self, generators: Sequence[Generator]) -> None:
        self.generators, self.turn = generators, 0

    async def generate(
        self, stage: str, task: str, value: str, schema: type[T], deadline: float
    ) -> T:
        generator = self.generators[self.turn % len(self.generators)]
        self.turn += 1
        return await generator.generate(stage, task, value, schema, deadline)


class Replay:
    """Serve recorded stage outputs in order, then delegate to a live generator."""

    def __init__(self, recorded: list[dict[str, object]], live: Generator | None) -> None:
        self.recorded, self.live = list(recorded), live

    async def generate(
        self, stage: str, task: str, value: str, schema: type[T], deadline: float
    ) -> T:
        if self.recorded and self.recorded[0]["stage"] == stage:
            return schema.model_validate(self.recorded.pop(0)["output"])
        if self.live is None:
            raise LookupError(f"no recorded output for stage {stage}")
        self.recorded.clear()
        return await self.live.generate(stage, task, value, schema, deadline)


class Recorder:
    def __init__(self, inner: Generator) -> None:
        self.inner = inner
        self.rows: list[dict[str, object]] = []

    async def generate(
        self, stage: str, task: str, value: str, schema: type[T], deadline: float
    ) -> T:
        result = await self.inner.generate(stage, task, value, schema, deadline)
        self.rows.append({"stage": stage, "output": result.model_dump(mode="json")})
        return result


def load_evidence(paths: Sequence[Path], cutoff: datetime) -> list[Evidence]:
    """Read exported news items (`{"items": [...]}`, as returned by MCP/API reads)."""
    items: dict[UUID, Evidence] = {}
    for path in paths:
        for raw in json.loads(path.read_text())["items"]:
            item = Evidence.model_validate({k: v for k, v in raw.items() if k in EVIDENCE_FIELDS})
            items[item.id] = item
    window = [e for e in items.values() if cutoff - timedelta(days=7) <= e.published_at < cutoff]
    return sorted(window, key=lambda e: (-e.published_at.timestamp(), str(e.id)))


def load_recording(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def render(artifact: Briefing) -> str:
    lines = [f"Generated {artifact.generated_at:%Y-%m-%d %H:%M} UTC", ""]
    if artifact.tldr:
        refs = "".join(f"[{n}]" for n in artifact.tldr.references)
        lines += ["**TL;DR**", "", f"{artifact.tldr.text} {refs}", ""]
    for section in artifact.sections:
        lines += [f"### {section.heading}", ""]
        for paragraph in section.paragraphs:
            refs = "".join(f"[{n}]" for n in paragraph.references)
            lines += [f"{paragraph.text} {refs}", ""]
    lines += ["**Sources**", ""]
    lines += [f"{c.number}. [{c.title}]({c.url})" for c in artifact.citations]
    return "\n".join(lines) + "\n"


def statistics(artifact: Briefing) -> dict[str, object]:
    words = sum(len(p.text.split()) for s in artifact.sections for p in s.paragraphs)
    return {
        "coverage": artifact.coverage,
        "evidence": artifact.evidence_count,
        "summary_words": words,
        "tldr_words": len(artifact.tldr.text.split()) if artifact.tldr else 0,
        "citations": len(artifact.citations),
        "headings": [s.heading for s in artifact.sections],
    }


async def run(
    arguments: argparse.Namespace,
    evidence: list[Evidence],
    cutoff: datetime,
    recorder_inner: list[dict[str, object]],
    recording: list[dict[str, object]],
) -> tuple[Briefing, Ledger]:
    from azure.identity.aio import AzureCliCredential

    ledger = Ledger()
    async with AzureCliCredential() as credential, httpx.AsyncClient(trust_env=False) as http:
        transport = ModelClient(
            http,
            credential,
            arguments.endpoint,
            TransportLimits(request_seconds=90, transport_attempts=1),
        )
        prices = (Decimal(arguments.input_price), Decimal(arguments.output_price))
        live = RoundRobin(
            [
                FoundryGenerator(transport, ledger, cutoff, name, *prices, "preview")
                for name in arguments.deployment
            ]
        )
        recorder = Recorder(Replay(recorder_inner, live))
        recorder.rows = recording
        artifact = await synthesize(recorder, evidence, cutoff, time.monotonic() + 3000)
    return artifact, ledger


def parse(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, nargs="+", required=True)
    parser.add_argument("--cutoff", type=datetime.fromisoformat)
    parser.add_argument("--replay", type=Path, help="recording.jsonl from an earlier preview")
    parser.add_argument("--out", type=Path, default=Path(".cache/briefing-preview"))
    parser.add_argument("--endpoint", default=os.environ.get("MODEL_ENDPOINT"))
    parser.add_argument(
        "--deployment", action="append", help="repeat to alternate same-model deployments"
    )
    parser.add_argument(
        "--input-price", default=os.environ.get("BRIEFING_INPUT_PRICE_PER_MILLION", "0")
    )
    parser.add_argument(
        "--output-price", default=os.environ.get("BRIEFING_OUTPUT_PRICE_PER_MILLION", "0")
    )
    arguments = parser.parse_args(argv)
    arguments.deployment = arguments.deployment or [os.environ.get("BRIEFING_DEPLOYMENT")]
    if not arguments.endpoint or not all(arguments.deployment):
        parser.error("set --endpoint/--deployment or MODEL_ENDPOINT/BRIEFING_DEPLOYMENT")
    return arguments


def main(argv: Sequence[str] | None = None) -> None:
    arguments = parse(argv)
    cutoff = arguments.cutoff or cutoff_at(datetime.now(UTC))
    evidence = load_evidence(arguments.input, cutoff)
    output: Path = arguments.out
    output.mkdir(parents=True, exist_ok=True)
    recorded = load_recording(arguments.replay) if arguments.replay else []
    recording: list[dict[str, object]] = []
    started = time.monotonic()
    try:
        artifact, ledger = asyncio.run(run(arguments, evidence, cutoff, recorded, recording))
    finally:
        # Keep completed stages even when a later stage fails, so it can be replayed.
        (output / "recording.jsonl").write_text("".join(json.dumps(r) + "\n" for r in recording))
    (output / "briefing.md").write_text(render(artifact))
    (output / "briefing.json").write_text(artifact.model_dump_json(indent=2))
    result = {
        **statistics(artifact),
        "live_calls": len(ledger.calls),
        "input_tokens": sum(c[1] for c in ledger.calls),
        "output_tokens": sum(c[2] for c in ledger.calls),
        "estimated_cost_usd": float(sum(c[3] for c in ledger.calls)),
        "seconds": round(time.monotonic() - started),
        "output": str(output / "briefing.md"),
    }
    print(json.dumps(result))


if __name__ == "__main__":
    main()
