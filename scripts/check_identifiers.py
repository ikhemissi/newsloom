"""Reject GUID-like deployment identifiers in repository files without printing their values."""

import re
import subprocess
import sys
from pathlib import Path

_GUID = re.compile(
    rb"(?i)(?<![0-9a-f])[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
    rb"[0-9a-f]{4}-[0-9a-f]{12}(?![0-9a-f])"
)
ROOT = Path(__file__).resolve().parents[1]


def find_identifiers(content: bytes) -> list[int]:
    return [
        number
        for number, line in enumerate(content.splitlines(), start=1)
        if _GUID.search(line) is not None
    ]


def main() -> int:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    failures = 0
    for name in sorted(set(result.stdout.split(b"\0")) - {b""}):
        path = ROOT / name.decode("utf-8")
        if not path.is_file():
            continue
        for line in find_identifiers(path.read_bytes()):
            print(
                f"{path.relative_to(ROOT)}:{line}: GUID-like identifier; "
                "keep deployment identifiers in ignored environment configuration.",
                file=sys.stderr,
            )
            failures += 1
    return int(failures > 0)


if __name__ == "__main__":
    raise SystemExit(main())
