"""Live editorial eval: the real briefing model on the synthetic golden week.

Skipped unless NEWSLOOM_LIVE_EVAL=1 (see scripts/eval.sh). Needs Azure CLI sign-in,
MODEL_ENDPOINT and BRIEFING_DEPLOYMENT; costs a few cents. Assertions are the
editorial rules, not exact wording.
"""

import asyncio
import os
import re
import time
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from newsloom_briefing.generation import FoundryGenerator, synthesize
from newsloom_briefing.preview import Ledger, load_evidence, render
from newsloom_core.briefing import Briefing
from newsloom_core.model_transport import ModelClient, TransportLimits
from test_briefing_golden import CUTOFF, GOLDEN, materialize

pytestmark = pytest.mark.skipif(
    os.environ.get("NEWSLOOM_LIVE_EVAL") != "1",
    reason="live model eval; run scripts/eval.sh --live",
)


async def generate(evidence_path: Path) -> Briefing:
    from azure.identity.aio import AzureCliCredential

    evidence = load_evidence([evidence_path], CUTOFF)
    async with AzureCliCredential() as credential, httpx.AsyncClient(trust_env=False) as http:
        transport = ModelClient(
            http,
            credential,
            os.environ["MODEL_ENDPOINT"],
            TransportLimits(request_seconds=90, transport_attempts=1),
        )
        generator = FoundryGenerator(
            transport,
            Ledger(),
            CUTOFF,
            os.environ["BRIEFING_DEPLOYMENT"],
            Decimal(0),
            Decimal(0),
            "live-eval",
        )
        return await synthesize(generator, evidence, CUTOFF, time.monotonic() + 900)


def test_live_briefing_follows_editorial_rules(tmp_path: Path) -> None:
    artifact = asyncio.run(generate(materialize(GOLDEN / "evidence.json", tmp_path / "e.json")))
    text = render(artifact)
    body = text.split("**Sources**")[0]
    assert artifact.coverage == "full" and artifact.tldr is not None
    assert "libcore" in body.casefold(), "security incident must be reported"
    assert "Model X 2.0" in body
    assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-", body), "no source IDs in prose"
    assert "Acme Vision" not in body, "vendor showcase is not a case study"
    assert "funding" not in body.casefold(), "routine funding news is excluded"
    paragraphs = [p.text for s in artifact.sections for p in s.paragraphs]
    assert len(paragraphs) == len(set(paragraphs))
    assert sum(len(p.split()) for p in paragraphs) + len(artifact.tldr.text.split()) <= 1000
    cases = [s for s in artifact.sections if s.heading == "Customer case studies"]
    if cases:
        assert all(p.text.endswith(").") for p in cases[0].paragraphs)
        assert "Invented Service" not in body
