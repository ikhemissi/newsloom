"""Operator repair of the Terraform state storage after a governance change."""

import pytest
from newsloom_platform import control
from newsloom_platform.config import PlatformFailure

ENV = {
    "RS_RESOURCE_GROUP": "rg-state",
    "RS_STORAGE_ACCOUNT": "ststate",
    "AZURE_SUBSCRIPTION_ID": "sub",
    "RESOURCE_TAGS": "Owner=team, Purpose = demo",
}
ACCOUNT = (
    "/subscriptions/sub/resourceGroups/rg-state/providers/Microsoft.Storage/storageAccounts/ststate"
)


def stub(monkeypatch: pytest.MonkeyPatch, access: str) -> list[list[str]]:
    calls: list[list[str]] = []

    def azure(arguments: list[str], category: str, *, timeout: int = 300) -> object:
        calls.append(arguments)
        if arguments[:3] == ["storage", "account", "show"]:
            return {"id": ACCOUNT}
        if arguments[:3] == ["storage", "account", "update"]:
            return {"publicNetworkAccess": access}
        return {}

    monkeypatch.setattr(control, "azure", azure)
    return calls


def test_tags_come_from_the_environment_and_both_targets_are_repaired(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = stub(monkeypatch, "Enabled")
    control.unblock_state(dict(ENV), "local")
    tagged = [c[c.index("--resource-id") + 1] for c in calls if c[:2] == ["tag", "update"]]
    assert tagged == ["/subscriptions/sub/resourceGroups/rg-state", ACCOUNT]
    assert all(
        c[-2:] == ["Owner=team", "Purpose=demo"] for c in calls if c[:2] == ["tag", "update"]
    )
    assert calls[-1][-2:] == ["--public-network-access", "Enabled"]


def test_a_reverted_access_setting_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    stub(monkeypatch, "Disabled")
    with pytest.raises(PlatformFailure, match="state_access_reverted"):
        control.unblock_state(dict(ENV), "local")


@pytest.mark.parametrize(
    ("tags", "category"), [("", "resource_tags_required"), ("broken", "invalid_resource_tags")]
)
def test_missing_or_malformed_tags_change_nothing(
    monkeypatch: pytest.MonkeyPatch, tags: str, category: str
) -> None:
    calls = stub(monkeypatch, "Enabled")
    with pytest.raises(PlatformFailure, match=category):
        control.unblock_state({**ENV, "RESOURCE_TAGS": tags}, "local")
    assert calls == []
