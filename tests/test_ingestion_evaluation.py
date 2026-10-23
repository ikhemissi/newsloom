import argparse
import asyncio
import json
import time
from pathlib import Path

import httpx
import pytest
from newsloom_ingestion import cli, evaluation
from newsloom_ingestion.evaluation import ReviewCase, compare, load_review, review_entries
from newsloom_ingestion.models import DEFAULT_LIMITS, Entry, IngestionFailure
from newsloom_ingestion.retrieval import PublicClient
from newsloom_ingestion.scanner import DecisionScanner, load_cases
from test_ingestion_database import entry
from test_ingestion_feeds import rss, source
from test_ingestion_scanner import Credential


def review() -> tuple[ReviewCase, ...]:
    return tuple(
        ReviewCase(
            id=f"review-{index:02}",
            source="fixture",
            guid=f"review-{index:02}",
            url=f"https://example.com/review-{index:02}",
            hostile=False,
            entry=entry().model_copy(
                update={
                    "source": "fixture",
                    "guid": f"review-{index:02}",
                    "url": f"https://example.com/review-{index:02}",
                    "text": "NEWSLOOM_CONTENT_CANARY",
                }
            ),
        )
        for index in range(23)
    )


class FixtureScanner(DecisionScanner):
    def __init__(self, client: httpx.AsyncClient, *, fail: str = "") -> None:
        super().__init__(client, Credential(), "https://example.com", "screen", None)
        self.cases = {case.entry.guid: case for case in load_cases()}
        self.fail = fail
        self.inputs: list[tuple[str, str]] = []

    async def baseline_score(self, text: str, deadline: float) -> float:
        self.inputs.append(("baseline", text))
        if self.fail == "authorization":
            raise IngestionFailure("scanner_http_403")
        return 0.9

    async def score(self, text: str, deadline: float) -> float:
        self.inputs.append(("candidate", text))
        guid = json.loads(text)["guid"]
        case = self.cases.get(guid)
        if case is None:
            return 0.1
        if self.fail == "holdout" and case.id == "v-topic":
            return 0.1
        if self.fail == "operational" and case.id == "v-release":
            raise IngestionFailure("scanner_http_429")
        if self.fail == "overlap":
            return 0.1
        return 0.9 if case.hostile else 0.1


@pytest.mark.parametrize("failure", ["", "holdout", "operational", "overlap", "authorization"])
async def test_complete_comparison_reports_measured_failures_without_content(failure: str) -> None:
    inputs = await review_entries(review(), (), time.monotonic() + 60)
    async with httpx.AsyncClient() as client:
        scanner = FixtureScanner(client, fail=failure)
        report = await compare(scanner, inputs, 0.5, "model", "1", time.monotonic() + 60)
    assert report["passed"] is (not failure)
    assert "CANARY" not in json.dumps(report)
    if failure != "authorization":
        assert len(scanner.inputs) == 126
        assert [text for variant, text in scanner.inputs if variant == "baseline"] == [
            text for variant, text in scanner.inputs if variant == "candidate"
        ]
    if not failure:
        assert report["candidate_threshold"] == 0.5
        assert isinstance(report["counts"], dict)
        assert report["counts"]["baseline"]["review"]["potential_false_positive"] == 23
        assert report["counts"]["candidate"]["review"]["potential_false_positive"] == 0
    else:
        assert isinstance(report["gates"], dict)
        assert not all(report["gates"].values())


def test_private_manifests_require_complete_unambiguous_identities(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    rows = [item.model_dump(mode="json") for item in review()]
    path.write_text(json.dumps(rows))
    assert len(load_review(path)) == 23
    for changed in (rows[:-1], [rows[0]] * 23, [{**rows[0], "hostile": "false"}, *rows[1:]]):
        path.write_text(json.dumps(changed))
        with pytest.raises(IngestionFailure, match="invalid_review_manifest"):
            load_review(path)
    with pytest.raises(IngestionFailure, match="evaluation_path_must_be_private"):
        evaluation.private_path(Path("docs/findings/private-inputs.json"))


@pytest.mark.parametrize("mode", ["success", "missing", "ambiguous"])
async def test_selected_feed_reconstruction_is_exact_and_records_provenance(
    mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from newsloom_ingestion.models import Document

    original = entry()
    case = ReviewCase(
        id="review-00", source=source().id, guid=original.guid, url=original.url, hostile=False
    )
    calls: list[str] = []

    class Client(PublicClient):
        async def fetch(
            self, url: str, headers: dict[str, str], deadline: float, *, robots: bool = False
        ) -> Document:
            calls.append(url)
            body = rss()
            if mode == "missing":
                body = body.replace(b"/article#part", b"/different")
            if mode == "ambiguous":
                body = body.replace(
                    b"</channel>",
                    body.split(b"<channel>")[1].split(b"</channel>")[0] + b"</channel>",
                )
            return Document(200, url, body, {})

    monkeypatch.setattr(evaluation, "PublicClient", Client)
    if mode == "success":
        result = await review_entries((case,), (source(),), time.monotonic() + 60)
        assert len(result) == 1
        assert result[0][1].model_dump_json() == original.model_dump_json()
        assert result[0][2:] == ("current_feed", "feed_item")
    else:
        with pytest.raises(IngestionFailure, match="review_identity_missing_or_ambiguous"):
            await review_entries((case,), (source(),), time.monotonic() + 60)
    assert calls == [str(source().url)]


async def test_evaluation_cli_never_initializes_production_and_writes_safe_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "manifest.json"
    report_path = tmp_path / "report.json"
    path.write_text(json.dumps([item.model_dump(mode="json") for item in review()]))
    for key, value in {
        "MODEL_ENDPOINT": "https://example.com",
        "SCREENING_DEPLOYMENT": "screen",
        "SCREENING_MODEL": "model",
        "SCREENING_VERSION": "1",
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("AZURE_CLIENT_ID", raising=False)

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Local evaluation attempted production initialization.")

    monkeypatch.setattr(cli, "ManagedIdentityCredential", forbidden)
    monkeypatch.setattr(cli, "Telemetry", forbidden)
    monkeypatch.setattr(cli, "Repository", forbidden)
    monkeypatch.setattr(cli, "AzureCliCredential", lambda **_: Credential())

    def scanner(
        client: httpx.AsyncClient,
        credential: object,
        endpoint: str,
        deployment: str,
        threshold: float | None,
    ) -> FixtureScanner:
        return FixtureScanner(client)

    monkeypatch.setattr(cli, "DecisionScanner", scanner)
    await cli.runtime(
        argparse.Namespace(
            command="evaluate",
            review_manifest=path,
            report=report_path,
            baseline_threshold=0.5,
            catalogue=Path("config/feeds.json"),
        ),
        "fixture",
    )
    assert json.loads(report_path.read_text())["passed"]
    assert "CANARY" not in report_path.read_text()
    assert report_path.stat().st_mode & 0o777 == 0o600
    files = await asyncio.to_thread(lambda: sorted(file.name for file in tmp_path.iterdir()))
    assert files == ["manifest.json", "report.json"]


async def test_authentication_preflight_does_not_fetch_articles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = tmp_path / "manifest.json"
    report_path = tmp_path / "report.json"
    manifest.write_text(json.dumps([item.model_dump(mode="json") for item in review()]))
    monkeypatch.setenv("MODEL_ENDPOINT", "https://example.com")
    monkeypatch.setenv("SCREENING_DEPLOYMENT", "screen")
    monkeypatch.setattr(cli, "AzureCliCredential", lambda **_: Credential())

    async def denied(self: DecisionScanner, text: str, deadline: float) -> float:
        raise IngestionFailure("scanner_http_403")

    async def forbidden(*args: object, **kwargs: object) -> tuple[()]:
        pytest.fail("Review content must not be fetched before inference authorization.")

    monkeypatch.setattr(DecisionScanner, "score", denied)
    monkeypatch.setattr(evaluation, "review_entries", forbidden)
    with pytest.raises(IngestionFailure, match="screening_evaluation_failed"):
        await cli.evaluate(
            argparse.Namespace(
                review_manifest=manifest,
                report=report_path,
                baseline_threshold=0.5,
                catalogue=Path("config/feeds.json"),
            )
        )
    assert json.loads(report_path.read_text())["error"] == "scanner_http_403"


@pytest.mark.parametrize("failure", ["", "holdout"])
async def test_existing_job_uses_only_managed_identity_and_safe_comparison_records(
    failure: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rows = [case.model_dump(mode="json", exclude={"entry"}) for case in review()]
    for key, value in {
        "AZURE_CLIENT_ID": "synthetic-client",
        "MODEL_ENDPOINT": "https://example.com",
        "SCREENING_DEPLOYMENT": "screen",
        "SCREENING_MODEL": "model",
        "SCREENING_VERSION": "1",
    }.items():
        monkeypatch.setenv(key, value)

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail(
            "Existing-job evaluation attempted developer auth or production initialization."
        )

    monkeypatch.setattr(cli, "AzureCliCredential", forbidden)
    monkeypatch.setattr(cli, "Telemetry", forbidden)
    monkeypatch.setattr(cli, "Repository", forbidden)
    identities: list[str] = []

    def identity(*, client_id: str) -> Credential:
        identities.append(client_id)
        return Credential()

    monkeypatch.setattr(cli, "ManagedIdentityCredential", identity)

    def scanner(
        client: httpx.AsyncClient,
        credential: object,
        endpoint: str,
        deployment: str,
        threshold: float | None,
    ) -> FixtureScanner:
        return FixtureScanner(client, fail=failure)

    monkeypatch.setattr(cli, "DecisionScanner", scanner)
    inputs = await review_entries(review(), (), time.monotonic() + 60)

    async def selected(
        *args: object,
    ) -> tuple[tuple[ReviewCase, Entry, evaluation.Provenance, str], ...]:
        return inputs

    monkeypatch.setattr(cli, "review_entries", selected)
    args = argparse.Namespace(
        command="evaluate-job",
        review_manifest_json=json.dumps(rows),
        baseline_threshold=0.5,
        catalogue=Path("config/feeds.json"),
    )
    if failure:
        with pytest.raises(IngestionFailure, match="screening_evaluation_failed"):
            await cli.runtime(args, "fixture")
    else:
        await cli.runtime(args, "fixture")
    assert identities == ["synthetic-client"]
    output = capsys.readouterr().out
    assert "CANARY" not in output and "https://example.com" not in output
    records = [json.loads(line) for line in output.splitlines()]
    assert len(records) == 127
    assert records[-1]["report"]["passed"] is (not failure)
    assert all(record["event"] == "screening_comparison_case" for record in records[:-1])
    assert all(len(line) < 4096 for line in output.splitlines())


async def test_job_arguments_cannot_carry_article_content(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Article content in job arguments must fail before authentication.")

    monkeypatch.setattr(cli, "ManagedIdentityCredential", forbidden)
    with pytest.raises(IngestionFailure, match="job_evaluation_requires_identities_only"):
        await cli.evaluate_job(
            argparse.Namespace(
                review_manifest_json=json.dumps([case.model_dump(mode="json") for case in review()])
            ),
            "fixture",
        )


def test_review_exports_must_match_identity_and_normalization_limits(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    items = review()
    assert items[0].entry is not None
    for change in ({"guid": "wrong"}, {"text": "x" * (DEFAULT_LIMITS.text_bytes + 1)}):
        changed = items[0].model_copy(update={"entry": items[0].entry.model_copy(update=change)})
        path.write_text(
            json.dumps([case.model_dump(mode="json") for case in (changed, *items[1:])])
        )
        with pytest.raises(IngestionFailure, match="invalid_review_manifest"):
            load_review(path)
