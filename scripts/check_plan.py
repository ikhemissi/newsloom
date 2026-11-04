"""Select check stages and test files from the files changed since a base revision.

Dependencies are derived from imports, so the map stays current without manual
upkeep: a test runs when it, a test helper it imports, a service it imports, or a
shared core module reachable from those changes. Anything unrecognised selects
everything; when unsure, run more.
"""

import argparse
import json
import re
import subprocess
from functools import cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = "packages/newsloom-core/src/newsloom_core/"
SERVICES = {p.name: f"services/{p.name}/" for p in (ROOT / "services").iterdir() if p.is_dir()}
PACKAGES = {f"newsloom_{name}": prefix for name, prefix in SERVICES.items()}

# Changes here can affect everything Python: dependency manifests, shared fixtures, tooling.
GLOBAL_PYTHON = (
    "pyproject.toml",
    "uv.lock",
    "packages/newsloom-core/pyproject.toml",
    "tests/conftest.py",
    "scripts/check.sh",
    "scripts/check_plan.py",
    ".github/workflows/",
)
EVALUATION = (
    "tools/agent-evaluation/",
    "scripts/agent_quality_",
    "scripts/check-agent-evaluation.sh",
    "config/agent-evaluation",
    "config/agent-quality",
    "pyproject.toml",
    "uv.lock",
    "services/agent/pyproject.toml",
    "packages/newsloom-core/pyproject.toml",
)
WEB = ("services/web/", "package.json", "package-lock.json", "scripts/check-ui-browser.sh")
# Files that never influence a check result.
INERT = re.compile(r"(^|/)(\.vscode|\.github/(skills|prompts))/|\.md$|^LICENSE$")
TERRAFORM_GLOBAL = ("azure.yaml", "infra/modules/", ".terraform-version")
IMPORT = re.compile(
    r"^\s*(?:from|import)\s+(newsloom_[a-z0-9_]+|test_[a-z0-9_]+)(?:\.([a-z0-9_]+))?", re.M
)


def changed_files(base: str) -> list[str]:
    def lines(*args: str) -> list[str]:
        return subprocess.run(
            ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
        ).stdout.split()

    committed = lines("diff", "--name-only", f"{base}...HEAD")
    working = lines("diff", "--name-only", "HEAD") + lines(
        "ls-files", "--others", "--exclude-standard"
    )
    return sorted(set(committed + working))


@cache
def imports(path: Path) -> frozenset[tuple[str, str]]:
    try:
        text = path.read_text()
    except OSError, UnicodeDecodeError:
        return frozenset()
    return frozenset((m.group(1), m.group(2) or "") for m in IMPORT.finditer(text))


@cache
def service_core_modules(service: str) -> frozenset[str]:
    """Core modules a service imports, directly or through other core modules."""
    found: set[str] = set()
    for source in (ROOT / SERVICES[service]).rglob("*.py"):
        found |= {mod for pkg, mod in imports(source) if pkg == "newsloom_core" and mod}
    return frozenset(core_closure(frozenset(found)))


def core_closure(modules: frozenset[str]) -> set[str]:
    pending, seen = list(modules), set(modules)
    while pending:
        source = ROOT / CORE / f"{pending.pop()}.py"
        for pkg, mod in imports(source):
            if pkg == "newsloom_core" and mod and mod not in seen:
                seen.add(mod)
                pending.append(mod)
    return seen


@cache
def service_services(service: str) -> frozenset[str]:
    """Other workspace services a service imports (for example platform -> mcp)."""
    found = {
        pkg.removeprefix("newsloom_")
        for source in (ROOT / SERVICES[service]).rglob("*.py")
        for pkg, _ in imports(source)
        if pkg in PACKAGES and pkg != f"newsloom_{service}"
    }
    return frozenset(found)


def dependencies(test: Path, seen: frozenset[Path] = frozenset()) -> tuple[set[str], set[str]]:
    """Path prefixes and core modules a test file depends on."""
    prefixes, modules = {str(test.relative_to(ROOT))}, set()
    services: set[str] = set()
    for pkg, mod in imports(test):
        if pkg == "newsloom_core":
            modules.add(mod) if mod else prefixes.add(CORE)
        elif pkg in PACKAGES:
            services.add(pkg.removeprefix("newsloom_"))
        elif pkg.startswith("test_") and (helper := test.parent / f"{pkg}.py") not in seen:
            more_prefixes, more_modules = dependencies(helper, seen | {test})
            prefixes |= more_prefixes
            modules |= more_modules
    pending = list(services)
    while pending:
        for other in service_services(pending.pop()):
            if other not in services:
                services.add(other)
                pending.append(other)
    for service in services:
        prefixes.add(SERVICES[service])
        modules |= service_core_modules(service)
    modules = core_closure(frozenset(modules))
    return prefixes, modules


def mentions(test: Path, path: str) -> bool:
    try:
        return path in test.read_text()
    except OSError:
        return False


def plan(changed: list[str]) -> dict[str, object]:
    relevant = [path for path in changed if not INERT.search(path)]
    everything = any(path.startswith(GLOBAL_PYTHON) for path in relevant)
    core_changed = {
        path.removeprefix(CORE).removesuffix(".py")
        for path in relevant
        if path.startswith(CORE) and path.endswith(".py")
    }
    if any(path.startswith("packages/") and not path.startswith(CORE) for path in relevant):
        everything = everything or any(p.endswith("pyproject.toml") for p in relevant)

    tests: list[str] = []
    for test in sorted((ROOT / "tests").glob("test_*.py")):
        name = str(test.relative_to(ROOT))
        prefixes, modules = dependencies(test)
        if (
            everything
            or modules & core_changed
            or any(path.startswith(tuple(prefixes)) for path in relevant)
            or any(
                path.startswith("tests/fixtures/") and mentions(test, path.split("/")[2])
                for path in relevant
            )
            or any(mentions(test, path) for path in relevant if "/" in path)
        ):
            tests.append(name)

    covered_prefixes = (
        "services/",
        "packages/",
        "tests/",
        "tools/",
        "infra/",
        "scripts/",
        "config/",
        "openspec/",
        "docs/",
        ".github/",
    )
    unknown = [
        p
        for p in relevant
        if not p.startswith(covered_prefixes)
        and p
        not in (
            *GLOBAL_PYTHON,
            *WEB,
            *TERRAFORM_GLOBAL,
            ".gitignore",
            ".dockerignore",
            "README.md",
            ".pre-commit-config.yaml",
            "AGENTS.md",
        )
    ]
    if unknown:
        everything = True
        tests = [str(t.relative_to(ROOT)) for t in sorted((ROOT / "tests").glob("test_*.py"))]

    web_fixture = ROOT / "services/web/tests/http_fixture.py"
    web_prefixes, web_modules = dependencies(web_fixture)
    web = (
        everything
        or any(p.startswith(WEB) for p in relevant)
        or bool(web_modules & core_changed)
        or any(p.startswith(tuple(web_prefixes)) for p in relevant)
    )

    layers = sorted(
        str(p.relative_to(ROOT))
        for p in (ROOT / "infra").rglob("*.tf")
        if p.parent.name != "tests" and ".terraform" not in p.parts
    )
    layer_dirs = sorted({str(Path(p).parent) for p in layers})
    if everything or any(p.startswith(TERRAFORM_GLOBAL) for p in relevant):
        terraform = layer_dirs
    else:
        terraform = sorted(
            {
                d
                for d in layer_dirs
                for p in relevant
                if p.startswith("infra/")
                and (Path(p).parent == Path(d) or Path(p).parent == Path(d) / "tests")
            }
        )

    return {
        "changed": len(changed),
        "everything": everything,
        "evaluation": everything or any(p.startswith(EVALUATION) for p in relevant),
        "python_tests": tests,
        "web": web,
        "terraform": terraform,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--base", help="revision to compare against, e.g. origin/main")
    group.add_argument("--files", nargs="*", help="explicit changed files (for tests)")
    group.add_argument("--all", action="store_true", help="select every stage")
    parser.add_argument("--shell", action="store_true", help="emit shell assignments")
    arguments = parser.parse_args()
    if arguments.all:
        result = plan(["pyproject.toml"])
    else:
        files = arguments.files if arguments.files is not None else changed_files(arguments.base)
        result = plan(files)
    if not arguments.shell:
        print(json.dumps(result))
        return
    print(f"EVERYTHING={int(bool(result['everything']))}")
    print(f"EVALUATION={int(bool(result['evaluation']))}")
    print(f"WEB={int(bool(result['web']))}")
    print(f"CHANGED={result['changed']}")
    print("PYTHON_TESTS='" + " ".join(result["python_tests"]) + "'")  # type: ignore[arg-type]
    print("TERRAFORM='" + " ".join(result["terraform"]) + "'")  # type: ignore[arg-type]


if __name__ == "__main__":
    main()
