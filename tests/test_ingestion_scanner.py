import time
from types import TracebackType

import httpx
import pytest
from azure.core.credentials import AccessToken
from azure.core.credentials_async import AsyncTokenCredential
from newsloom_ingestion.models import IngestionFailure
from newsloom_ingestion.scanner import DecisionScanner, calibrate, probability, select_threshold
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
            values = [0.1] * 4 + [0.9] * 4 + [0.2] * 4 + [0.8] * 4
            if bad_holdout:
                values[-1] = 0.2
            self.scores = iter(values)

        async def score(self, text: str, deadline: float) -> float:
            return next(self.scores)

    async with httpx.AsyncClient() as client:
        scanner = FixtureScanner(client)
        if bad_holdout:
            with pytest.raises(IngestionFailure, match="scanner_validation_failed"):
                await calibrate(scanner, time.monotonic() + 60)
        else:
            result = await calibrate(scanner, time.monotonic() + 60)
            assert result["threshold"] == 0.5
            assert result["validation_cases"] == 8
            assert result["validation_errors"] == 0


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
