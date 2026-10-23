"""Private local inputs and content-free, paired screening observations."""

import json
import math
import time
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Annotated, Literal

from newsloom_core.feeds import FeedSource
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from newsloom_ingestion.articles import recover
from newsloom_ingestion.models import DEFAULT_LIMITS, Entry, IngestionFailure
from newsloom_ingestion.parsing import parse
from newsloom_ingestion.retrieval import PublicClient
from newsloom_ingestion.scanner import (
    BASELINE_QUESTION,
    QUESTION,
    CalibrationCase,
    DecisionScanner,
    calibration_id,
    fixture_bytes,
    load_cases,
    select_threshold,
)

Provenance = Literal["authored_fixture", "current_feed", "stored_export"]


class ReviewCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    id: Annotated[str, Field(pattern=r"^review-[0-9]{2}$")]
    source: str
    guid: str | None
    url: str
    hostile: Annotated[bool, Field(strict=True)]
    entry: Entry | None = None


class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    split: Literal["calibration", "validation", "regression", "review"]
    family: str
    hostile: bool
    variant: Literal["baseline", "candidate"]
    score: float | None
    error: str | None
    input_fingerprint: str
    provenance: Provenance
    acquired_at: str
    acquisition_path: str
    at_text_limit: bool


def private_path(path: Path) -> Path:
    resolved = path.resolve()
    roots = [parent for parent in Path(__file__).resolve().parents if (parent / ".git").exists()]
    roots.extend(
        parent for parent in (Path.cwd(), *Path.cwd().parents) if (parent / ".git").exists()
    )
    if any(resolved.is_relative_to(root) for root in roots):
        raise IngestionFailure("evaluation_path_must_be_private")
    return resolved


def load_review(path: Path) -> tuple[ReviewCase, ...]:
    path = private_path(path)
    if path.stat().st_size > 4 * 1024 * 1024:
        raise IngestionFailure("review_manifest_size")
    return parse_review(path.read_bytes())


def parse_review(data: bytes) -> tuple[ReviewCase, ...]:
    if len(data) > 4 * 1024 * 1024:
        raise IngestionFailure("review_manifest_size")
    try:
        cases = TypeAdapter(tuple[ReviewCase, ...]).validate_json(data)
    except ValidationError:
        raise IngestionFailure("invalid_review_manifest") from None
    if (
        len(cases) != 23
        or len({case.id for case in cases}) != 23
        or len({(case.source, case.guid, case.url) for case in cases}) != 23
        or len({case.source for case in cases}) > 3
        or any(
            case.entry is not None
            and (
                (case.entry.source, case.entry.guid, case.entry.url)
                != (case.source, case.guid, case.url)
                or len(case.entry.text.encode()) > DEFAULT_LIMITS.text_bytes
            )
            for case in cases
        )
    ):
        raise IngestionFailure("invalid_review_manifest")
    return cases


async def review_entries(
    cases: tuple[ReviewCase, ...],
    sources: tuple[FeedSource, ...],
    deadline: float,
) -> tuple[tuple[ReviewCase, Entry, Provenance, str], ...]:
    selected = {case.source for case in cases if case.entry is None}
    catalogue = {source.id: source for source in sources}
    if selected - catalogue.keys():
        raise IngestionFailure("unknown_review_source")
    entries: dict[str, tuple[Entry, Provenance, str]] = {
        case.id: (case.entry, "stored_export", "stored") for case in cases if case.entry is not None
    }
    client = PublicClient(DEFAULT_LIMITS)
    # No on-disk article cache: both policies consume these same in-memory entries.
    for identifier in sorted(selected):
        source = catalogue[identifier]
        feed_deadline = min(deadline, time.monotonic() + DEFAULT_LIMITS.feed_seconds)
        document = await client.fetch(str(source.url), {}, feed_deadline)
        if document.status != 200:
            raise IngestionFailure(f"review_feed_http_{document.status}")
        parsed = parse(source, document.body, document.url, datetime.now(UTC))
        for case in cases:
            if case.source != identifier or case.entry is not None:
                continue
            matches = [
                item
                for item in parsed.candidates
                if item.guid == case.guid and item.url == case.url
            ]
            if len(matches) != 1:
                raise IngestionFailure("review_identity_missing_or_ambiguous")
            candidate = matches[0]
            path = "feed_item"
            if not candidate.title or not candidate.text:
                candidate, path = await recover(candidate, client, feed_deadline, "evaluation")
            try:
                item = candidate.entry()
            except ValidationError:
                raise IngestionFailure("invalid_review_entry") from None
            entries[case.id] = (item, "current_feed", path)
    return tuple((case, *entries[case.id]) for case in cases)


async def compare(
    scanner: DecisionScanner,
    review: tuple[tuple[ReviewCase, Entry, Provenance, str], ...],
    baseline_threshold: float,
    model: str,
    version: str,
    deadline: float,
) -> dict[str, object]:
    if not math.isfinite(baseline_threshold) or not 0 <= baseline_threshold <= 1:
        raise IngestionFailure("invalid_baseline_threshold")
    if len(review) != 23 or len({case.id for case, _, _, _ in review}) != 23:
        raise IngestionFailure("incomplete_review_set")
    cases = load_cases()
    acquired_at = datetime.now(UTC).isoformat()
    inputs: list[tuple[CalibrationCase | ReviewCase, Entry, Provenance, str]] = [
        (case, case.entry, "authored_fixture", "fixture") for case in cases
    ] + list(review)
    observations: list[Observation] = []
    for variant in ("baseline", "candidate"):
        for case, entry, provenance, path in inputs:
            text = entry.model_dump_json()
            score = None
            error = None
            try:
                score = await (
                    scanner.baseline_score(text, deadline)
                    if variant == "baseline"
                    else scanner.score(text, deadline)
                )
            except IngestionFailure as failure:
                error = str(failure)
            observations.append(
                Observation(
                    id=case.id,
                    split=case.split if isinstance(case, CalibrationCase) else "review",
                    family=case.family if isinstance(case, CalibrationCase) else "review",
                    hostile=case.hostile,
                    variant=variant,
                    score=score,
                    error=error,
                    input_fingerprint=sha256(text.encode()).hexdigest(),
                    provenance=provenance,
                    acquired_at=acquired_at,
                    acquisition_path=path,
                    at_text_limit=len(entry.text.encode()) >= DEFAULT_LIMITS.text_bytes,
                )
            )
            if error in ("scanner_http_401", "scanner_http_403", "scanner_unavailable"):
                return summarize(
                    observations, baseline_threshold, scanner, model, version, len(inputs) * 2
                )
    return summarize(observations, baseline_threshold, scanner, model, version, len(inputs) * 2)


def summarize(
    observations: list[Observation],
    baseline_threshold: float,
    scanner: DecisionScanner,
    model: str,
    version: str,
    expected_observations: int,
) -> dict[str, object]:
    candidate_calibration = [
        item for item in observations if item.variant == "candidate" and item.split == "calibration"
    ]
    threshold = None
    calibration_error = None
    if len(candidate_calibration) == 16 and all(
        item.score is not None for item in candidate_calibration
    ):
        try:
            threshold = select_threshold(
                [
                    item.score
                    for item in candidate_calibration
                    if not item.hostile and item.score is not None
                ],
                [
                    item.score
                    for item in candidate_calibration
                    if item.hostile and item.score is not None
                ],
            )
        except IngestionFailure as error:
            calibration_error = str(error)
    else:
        calibration_error = "incomplete_calibration"
    rows: list[dict[str, object]] = []
    for item in observations:
        gate = baseline_threshold if item.variant == "baseline" else threshold
        rejected = item.score > gate if item.score is not None and gate is not None else None
        rows.append(
            {
                **item.model_dump(),
                "threshold": gate,
                "disposition": (
                    "deferred"
                    if item.error
                    else "unclassified"
                    if rejected is None
                    else "rejected"
                    if rejected
                    else "accepted"
                ),
                "reason": (
                    item.error or "calibration_unavailable"
                    if rejected is None
                    else "prompt_injection"
                    if rejected
                    else "screened"
                ),
                "potential_false_positive": rejected is True and not item.hostile,
                "hostile_acceptance": rejected is False and item.hostile,
            }
        )
    counts = {
        variant: {
            split: {
                "cases": sum(row["variant"] == variant and row["split"] == split for row in rows),
                **{
                    metric: sum(
                        row["variant"] == variant and row["split"] == split and bool(row[metric])
                        for row in rows
                    )
                    for metric in ("potential_false_positive", "hostile_acceptance", "error")
                },
            }
            for split in ("calibration", "validation", "regression", "review")
        }
        for variant in ("baseline", "candidate")
    }
    candidate = counts["candidate"]
    gates = {
        "complete_inference": len(rows) == expected_observations
        and all(row["error"] is None for row in rows),
        "separable_calibration": threshold is not None,
        "zero_holdout_errors": candidate["validation"]["cases"] == 16
        and candidate["validation"]["potential_false_positive"] == 0
        and candidate["validation"]["hostile_acceptance"] == 0
        and candidate["validation"]["error"] == 0
        and threshold is not None,
        "legacy_regressions": candidate["regression"]["cases"] == 8
        and candidate["regression"]["hostile_acceptance"] == 0
        and candidate["regression"]["error"] == 0
        and threshold is not None,
        "fewer_review_false_positives": candidate["review"]["cases"] == 23
        and counts["baseline"]["review"]["cases"] == 23
        and candidate["review"]["potential_false_positive"]
        < counts["baseline"]["review"]["potential_false_positive"]
        and threshold is not None,
    }
    endpoint = scanner.endpoint.removesuffix("/providers/microsoft/v1/systemone")
    return {
        "passed": all(gates.values()),
        "gates": gates,
        "counts": counts,
        "calibration_error": calibration_error,
        "candidate_threshold": threshold,
        "baseline_threshold": baseline_threshold,
        "calibration_id": (
            calibration_id(endpoint, scanner.deployment, model, version, threshold)
            if threshold is not None
            else None
        ),
        "fixture_revision": sha256(fixture_bytes()).hexdigest(),
        "candidate_revision": sha256(QUESTION.encode()).hexdigest(),
        "baseline_revision": sha256(BASELINE_QUESTION.encode()).hexdigest(),
        "model_configuration": sha256(
            json.dumps([endpoint, scanner.deployment, model, version]).encode()
        ).hexdigest(),
        "expected_observations": expected_observations,
        "observations": rows,
    }
