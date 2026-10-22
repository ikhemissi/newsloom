import json
from pathlib import Path

import pytest
from newsloom_core.feeds import load_feed_catalogue, main
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]


def write_catalogue(tmp_path: Path, data: object) -> Path:
    path = tmp_path / "feeds.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def feed(**overrides: object) -> dict[str, object]:
    return {
        "id": "example-feed",
        "title": "Example feed",
        "url": "https://example.com/feed.xml",
        "kind": "rss",
    } | overrides


def test_initial_catalogue() -> None:
    sources = load_feed_catalogue(ROOT / "config" / "feeds.json")
    assert len(sources) == 42
    assert len({source.id for source in sources}) == 42
    assert sum(source.kind == "atom" for source in sources) == 2
    filtered = {source.id: source.include_categories for source in sources}
    assert filtered["azure-updates"] == (
        "AI + machine learning",
        "Microsoft Foundry",
        "Azure AI Foundry",
        "Azure Copilot",
    )
    assert filtered["linuxfoundation-blog"] == ("AI/ML",)
    assert filtered["aws-whats-new"] is not None


@pytest.mark.parametrize("kind", ["rss", "atom"])
def test_valid_feed(tmp_path: Path, kind: str) -> None:
    source = load_feed_catalogue(write_catalogue(tmp_path, [feed(kind=kind)]))[0]
    assert source.id == "example-feed"
    assert source.kind == kind
    assert source.include_categories is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"id": "Not a slug"},
        {"title": ""},
        {"title": "   "},
        {"url": "not-a-url"},
        {"url": "http://example.com/feed"},
        {"url": "https://user:password@example.com/feed"},
        {"kind": "json"},
        {"include_categories": []},
        {"include_categories": [" "]},
        {"include_categories": [12]},
        {"unknown": True},
    ],
)
def test_invalid_feed_is_rejected(tmp_path: Path, overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        load_feed_catalogue(write_catalogue(tmp_path, [feed(**overrides)]))


def test_validation_errors_do_not_echo_credentials(tmp_path: Path) -> None:
    url = "https://feed-user:feed-password@example.com/feed"
    path = write_catalogue(tmp_path, [feed(url=url)])
    with pytest.raises(ValidationError) as error:
        load_feed_catalogue(path)
    assert "Feed URLs must not contain credentials" in str(error.value)
    assert "feed-user" not in str(error.value)
    assert "feed-password" not in str(error.value)


@pytest.mark.parametrize("data", [[], {}, {"feeds": []}])
def test_invalid_catalogue_shape(tmp_path: Path, data: object) -> None:
    with pytest.raises(ValidationError):
        load_feed_catalogue(write_catalogue(tmp_path, data))


def test_duplicate_ids(tmp_path: Path) -> None:
    path = write_catalogue(tmp_path, [feed(), feed(url="https://example.org/feed")])
    with pytest.raises(ValueError, match="IDs must be unique"):
        load_feed_catalogue(path)


def test_duplicate_urls(tmp_path: Path) -> None:
    path = write_catalogue(tmp_path, [feed(), feed(id="different-id")])
    with pytest.raises(ValueError, match="URLs must be unique"):
        load_feed_catalogue(path)


def test_missing_catalogue(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_feed_catalogue(tmp_path / "missing.json")


def test_malformed_json(tmp_path: Path) -> None:
    path = tmp_path / "feeds.json"
    path.write_text("{", encoding="utf-8")
    with pytest.raises(ValidationError):
        load_feed_catalogue(path)


def test_cli(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr("sys.argv", ["newsloom-validate-feeds", str(ROOT / "config/feeds.json")])
    main()
    assert "Validated 42 feed sources" in capsys.readouterr().out
