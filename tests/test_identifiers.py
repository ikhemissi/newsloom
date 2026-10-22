import subprocess
from pathlib import Path

import pytest

from scripts import check_identifiers


def test_reports_lines_without_needing_literal_identifiers() -> None:
    identifier = b"-".join([b"a" * 8, b"b" * 4, b"c" * 4, b"d" * 4, b"e" * 12])
    assert check_identifiers.find_identifiers(b"safe\n" + identifier.upper() + b"\nsafe") == [2]
    assert check_identifiers.find_identifiers(b"a" + identifier + b"b") == []
    assert check_identifiers.find_identifiers(b"${AZURE_TENANT_ID}") == []


def test_checks_untracked_files_and_ignores_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text(".env\n", encoding="utf-8")
    identifier = "-".join(["a" * 8, "b" * 4, "c" * 4, "d" * 4, "e" * 12])
    (tmp_path / ".env").write_text(identifier, encoding="utf-8")
    monkeypatch.setattr(check_identifiers, "ROOT", tmp_path)
    assert check_identifiers.main() == 0
    (tmp_path / "config.txt").write_text(identifier, encoding="utf-8")
    assert check_identifiers.main() == 1
    message = capsys.readouterr().err
    assert "config.txt:1" in message
    assert identifier not in message
