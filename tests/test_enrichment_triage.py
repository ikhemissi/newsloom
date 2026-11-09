import json
import time

import httpx
import pytest
from newsloom_core.model_transport import ModelClient
from newsloom_enrichment.models import Announcement, EnrichmentFailure
from newsloom_enrichment.triage import INSTRUCTIONS, FoundryTriage, Rating, Triage, checked
from test_ingestion_scanner import Credential


def announcement(statement: str = "Widget reached GA.") -> Announcement:
    return Announcement.model_validate(
        {
            "statement": statement,
            "change_type": "availability",
            "status": "ga",
            "effective_date": None,
            "deadline": None,
            "products": [{"product": "Widget", "vendor": "Acme"}],
        }
    )


def rating(index: int, **change: object) -> dict[str, object]:
    return {
        "index": index,
        "tier": "worth_knowing",
        "reason": "Changes how agents call tools.",
        "capability": "agent tools",
        **change,
    }


def test_ratings_must_cover_every_announcement_once() -> None:
    result = Triage.model_validate({"ratings": [rating(1), rating(0)]})
    assert [item.index for item in checked(result, 2)] == [0, 1]
    for ratings in ([rating(0)], [rating(0), rating(0)], [rating(0), rating(2)]):
        with pytest.raises(EnrichmentFailure, match="invalid_triage"):
            checked(Triage.model_validate({"ratings": ratings}), 2)


def test_reason_length_and_capability_vocabulary() -> None:
    assert Rating.model_validate(rating(0, capability=" Agent  Tools ")).capability == "agent tools"
    assert Rating.model_validate(rating(0, capability="Widget Pro")).capability == "other"
    with pytest.raises(ValueError):
        Rating.model_validate(rating(0, reason=" ".join(["word"] * 21)))
    with pytest.raises(ValueError):
        Rating.model_validate(rating(0, tier="urgent"))


async def test_triage_sends_only_derived_data_and_validates_output() -> None:
    sent: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        sent.append(body)
        content = json.dumps({"ratings": [rating(0, tier="act_now")]})
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        triage = FoundryTriage(ModelClient(client, Credential(), "https://example.com"), "gen")
        ratings = await triage.rate(
            "Title", "Summary.", "announcement", (announcement(),), time.monotonic() + 60
        )
        assert [item.tier for item in ratings] == ["act_now"]
        assert await triage.rate("T", "S.", "other", (), time.monotonic() + 60) == ()
    assert len(sent) == 1
    messages = sent[0]["messages"]
    assert isinstance(messages, list) and messages[0]["content"] == INSTRUCTIONS
    payload = json.loads(messages[1]["content"])
    assert set(payload) == {"title", "summary", "article_kind", "announcements"}
    assert payload["announcements"][0]["products"] == ["Widget (Acme)"]
    assert "default" not in json.dumps(sent[0]["response_format"])
