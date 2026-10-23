import json
import time
from types import TracebackType

import httpx
import pytest
from azure.core.credentials import AccessToken
from azure.core.credentials_async import AsyncTokenCredential
from newsloom_ingestion import scanner as scanner_module
from newsloom_ingestion.models import IngestionFailure
from newsloom_ingestion.scanner import (
    BASELINE_QUESTION,
    QUESTION,
    DecisionScanner,
    calibrate,
    calibration_id,
    load_cases,
    probability,
    select_threshold,
)
from test_ingestion_database import entry


class Credential(AsyncTokenCredential):
    async def get_token(self, *scopes: str, **kwargs: object) -> AccessToken:
        return AccessToken("synthetic-test-token", int(time.time()) + 3600)

    async def close(self) -> None:
        return None

    async def __aenter__(self) -> Credential:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ) -> None:
        await self.close()


@pytest.mark.parametrize("score", [0, 0.1, 1])
def test_finite_noul_contract(score: float) -> None:
    assert probability({"answers": {"injection": {"type": "noul", "noul": score}}}) == score


@pytest.mark.parametrize("score", [True, False, None, "0.5", -0.1, 1.1, float("inf"), float("nan")])
def test_bad_probabilities_cannot_admit(score: object) -> None:
    with pytest.raises(IngestionFailure):
        probability({"answers": {"injection": {"type": "noul", "noul": score}}})


def test_calibration_is_derived_not_defaulted() -> None:
    assert select_threshold([0, 0.2], [0.8, 1]) == 0.5
    for clean, hostile in [([], [1.0]), ([0.9], [0.2]), ([0.5], [0.5])]:
        with pytest.raises(IngestionFailure):
            select_threshold(clean, hostile)


@pytest.mark.parametrize(
    "score,expected", [(0.1, "accepted"), (0.5, "accepted"), (0.9, "rejected")]
)
async def test_actual_adapter_payload_and_verdict(score: float, expected: str) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/providers/microsoft/v1/systemone"
        assert request.headers["Authorization"].startswith("Bearer ")
        payload = json.loads(request.content)
        assert payload["state"] == entry().model_dump_json()
        assert payload["questions"]["injection"]["instructions"] == QUESTION
        return httpx.Response(200, json={"answers": {"injection": {"type": "noul", "noul": score}}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        scanner = DecisionScanner(
            client, Credential(), "https://test.services.ai.azure.com", "screen", 0.5
        )
        assert (await scanner.scan(entry(), time.monotonic() + 60)).disposition == expected


@pytest.mark.parametrize("status", [401, 403, 400])
async def test_http_failure_is_deferred_not_rejected(status: int) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(status))
    ) as client:
        scanner = DecisionScanner(
            client, Credential(), "https://test.services.ai.azure.com", "screen", 0.5
        )
        decision = await scanner.scan(entry(), time.monotonic() + 60)
        assert decision.disposition == "deferred"
        assert decision.reason == f"scanner_http_{status}"


async def test_missing_threshold_and_throttling_never_accept() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(429, headers={"Retry-After": "120"}))
    ) as client:
        scanner = DecisionScanner(
            client, Credential(), "https://test.services.ai.azure.com", "screen", None
        )
        with pytest.raises(IngestionFailure, match="threshold_required"):
            await scanner.scan(entry(), time.monotonic() + 60)
        scanner.threshold = 0.5
        assert (await scanner.scan(entry(), time.monotonic() + 10)).disposition == "deferred"


async def test_separate_validation_is_required() -> None:
    class FixtureScanner(DecisionScanner):
        async def score(self, text: str, deadline: float) -> float:
            return 0.1

    async with httpx.AsyncClient() as client:
        scanner = FixtureScanner(
            client, Credential(), "https://test.services.ai.azure.com", "screen", None
        )
        with pytest.raises(IngestionFailure, match="calibration_not_separable"):
            await calibrate(scanner, time.monotonic() + 60)


def test_payload_type_and_guessed_probability_field_are_rejected() -> None:
    values: list[object] = [
        None,
        [],
        {"answers": {"injection": {"type": "noul", "probability": 0.1}}},
    ]
    for value in values:
        with pytest.raises(IngestionFailure):
            probability(value)


@pytest.mark.parametrize("bad_holdout", [False, True])
async def test_calibration_does_not_train_on_the_validation_set(bad_holdout: bool) -> None:
    class FixtureScanner(DecisionScanner):
        def __init__(self, client: httpx.AsyncClient) -> None:
            super().__init__(
                client, Credential(), "https://test.services.ai.azure.com", "screen", None
            )
            self.cases = {case.entry.guid: case for case in load_cases()}

        async def score(self, text: str, deadline: float) -> float:
            case = self.cases[json.loads(text)["guid"]]
            if bad_holdout and case.id == "v-topic":
                return 0.2
            if case.split == "calibration":
                return 0.9 if case.hostile else 0.1
            return 0.8 if case.hostile else 0.2

    async with httpx.AsyncClient() as client:
        scanner = FixtureScanner(client)
        if bad_holdout:
            with pytest.raises(IngestionFailure, match="scanner_validation_failed"):
                await calibrate(scanner, time.monotonic() + 60)
        else:
            result = await calibrate(scanner, time.monotonic() + 60)
            assert result["threshold"] == 0.5
            assert result["calibration_cases"] == result["validation_cases"] == 16
            assert result["regression_cases"] == 8
            assert result["validation_errors"] == 0


def test_complete_typed_fixtures_cover_context_metadata_and_legacy() -> None:
    cases = load_cases()
    assert len(cases) == len({case.id for case in cases}) == 40
    for split in ("calibration", "validation"):
        for hostile in (False, True):
            assert sum(case.split == split and case.hostile == hostile for case in cases) == 8
        families = {case.family for case in cases if case.split == split}
        assert {"training_notice", "quoted_prompt", "security_reporting", "metadata"} <= families
    assert sum(case.split == "regression" and case.hostile for case in cases) == 8


@pytest.mark.parametrize("problem", ["duplicate", "label", "split", "oversized"])
def test_invalid_fixtures_fail_with_content_free_categories(
    problem: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    cases = [case.model_dump(mode="json") for case in load_cases()]
    if problem == "duplicate":
        cases[1] = cases[0]
    elif problem == "label":
        cases[0]["hostile"] = "false"
    elif problem == "split":
        cases = [case for case in cases if case["split"] != "validation"]
    else:
        cases[0]["entry"]["text"] = "x" * (32 * 1024 + 1)
    monkeypatch.setattr(scanner_module, "fixture_bytes", lambda: json.dumps(cases).encode())
    with pytest.raises(IngestionFailure, match=r"^invalid_calibration_fixture$"):
        load_cases()


def test_binding_covers_policy_fixtures_model_and_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = calibration_id("https://example.com", "screen", "Microsoft-Decision-1", "1", 0.5)
    assert len(original) == 64
    assert original == calibration_id(
        "https://example.com/", "screen", "Microsoft-Decision-1", "1", 0.5
    )
    for endpoint, deployment, model, version, threshold in [
        ("https://other.example.com", "screen", "Microsoft-Decision-1", "1", 0.5),
        ("https://example.com", "different", "Microsoft-Decision-1", "1", 0.5),
        ("https://example.com", "screen", "different", "1", 0.5),
        ("https://example.com", "screen", "Microsoft-Decision-1", "2", 0.5),
        ("https://example.com", "screen", "Microsoft-Decision-1", "1", 0.6),
    ]:
        assert calibration_id(endpoint, deployment, model, version, threshold) != original
    data = scanner_module.fixture_bytes()
    monkeypatch.setattr(scanner_module, "fixture_bytes", lambda: data + b" ")
    assert (
        calibration_id("https://example.com", "screen", "Microsoft-Decision-1", "1", 0.5)
        != original
    )
    monkeypatch.setattr(scanner_module, "fixture_bytes", lambda: data)
    monkeypatch.setattr(scanner_module, "QUESTION", "changed rubric")
    assert (
        calibration_id("https://example.com", "screen", "Microsoft-Decision-1", "1", 0.5)
        != original
    )


async def test_full_length_body_and_metadata_are_not_shortened() -> None:
    item = entry().model_copy(
        update={
            "text": "x" * (32 * 1024),
            "title": "Instruction in the title",
            "author": "Instruction in the author",
            "categories": ("Instruction in categories",),
        }
    )

    def handle(request: httpx.Request) -> httpx.Response:
        state = json.loads(json.loads(request.content)["state"])
        assert state == item.model_dump(mode="json")
        assert len(state["text"].encode()) == 32 * 1024
        return httpx.Response(200, json={"answers": {"injection": {"type": "noul", "noul": 0.1}}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        scanner = DecisionScanner(client, Credential(), "https://example.com", "screen", 0.5)
        assert (await scanner.scan(item, time.monotonic() + 60)).disposition == "accepted"


async def test_baseline_and_candidate_share_one_retry_and_rate_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [100.0]
    requests: list[tuple[float, str]] = []

    async def sleep(seconds: float) -> None:
        clock[0] += seconds

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(
            (clock[0], json.loads(request.content)["questions"]["injection"]["instructions"])
        )
        return httpx.Response(200, json={"answers": {"injection": {"type": "noul", "noul": 0.1}}})

    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    monkeypatch.setattr("newsloom_ingestion.scanner.asyncio.sleep", sleep)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        scanner = DecisionScanner(client, Credential(), "https://example.com", "screen", None)
        await scanner.baseline_score(entry().model_dump_json(), 160)
        await scanner.score(entry().model_dump_json(), 160)
    assert requests == [(100.0, BASELINE_QUESTION), (101.0, QUESTION)]


async def test_retries_are_rate_limited_and_exactly_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [100.0]
    calls: list[float] = []

    async def sleep(seconds: float) -> None:
        clock[0] += seconds

    def response(request: httpx.Request) -> httpx.Response:
        calls.append(clock[0])
        return httpx.Response(503, headers={"Retry-After": "2"})

    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    monkeypatch.setattr("newsloom_ingestion.scanner.asyncio.sleep", sleep)
    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
        scanner = DecisionScanner(
            client, Credential(), "https://test.services.ai.azure.com", "screen", 0.5
        )
        result = await scanner.scan(entry(), 160)
        assert result.disposition == "deferred" and result.reason == "scanner_http_503"
        assert calls == [100.0, 102.0, 104.0]
        calls.clear()
        scanner.next_request = 200
        result = await scanner.scan(entry(), 160)
        assert result.disposition == "deferred" and result.reason == "scanner_deadline"
        assert calls == []
