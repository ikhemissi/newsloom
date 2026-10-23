"""Operator actions used by azd hooks; never provisions resources directly."""

import hashlib
import json
import re
import subprocess
import tempfile
import time
from pathlib import Path

from newsloom_platform.config import PlatformFailure, json_object, text_field
from newsloom_platform.events import event

API_VERSION = "2025-07-01"


def run(arguments: list[str], category: str, *, timeout: int = 300) -> str:
    result = subprocess.run(arguments, text=True, capture_output=True, timeout=timeout, check=False)
    if result.returncode:
        raise PlatformFailure(f"command_failed_{category}")
    return result.stdout.strip()


def azure(arguments: list[str], category: str, *, timeout: int = 300) -> object:
    output = run(
        ["az", *arguments, "--only-show-errors", "--output", "json"], category, timeout=timeout
    )
    try:
        return json.loads(output)
    except json.JSONDecodeError as error:
        raise PlatformFailure(f"invalid_command_response_{category}") from error


def environment() -> dict[str, str]:
    value = json_object(
        json.loads(run(["azd", "env", "get-values", "--output", "json"], "environment"))
    )
    result: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(item, str):
            raise PlatformFailure("invalid_environment_value")
        result[key] = item
    return result


def set_environment(name: str, value: str) -> None:
    run(["azd", "env", "set", name, value], "environment_update")


def rest(url: str, category: str, *, body: object | None = None, resource: str = "") -> object:
    arguments = ["rest", "--url", url]
    if resource:
        arguments.extend(["--resource", resource])
    if body is None:
        return azure(arguments, category)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json") as temporary:
        json.dump(body, temporary)
        temporary.flush()
        return azure([*arguments, "--method", "post", "--body", f"@{temporary.name}"], category)


def source_hash(root: Path) -> str:
    paths = {
        Path("pyproject.toml"),
        Path("uv.lock"),
        Path("README.md"),
        Path(".dockerignore"),
    }
    for raw in run(
        ["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        "image_source",
    ).split("\0"):
        if raw and (raw.startswith(("packages/", "services/")) or raw == "config/feeds.json"):
            paths.add(Path(raw))
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(str(path).encode() + b"\0" + (root / path).read_bytes() + b"\0")
    return digest.hexdigest()


def build(env: dict[str, str], correlation: str, *, ingestion: bool = False) -> None:
    service = "ingestion" if ingestion else "platform"
    repository = f"newsloom-{service}"
    registry = env["AZURE_CONTAINER_REGISTRY_NAME"]
    root = Path(run(["git", "rev-parse", "--show-toplevel"], "project_root"))
    tag = source_hash(root)
    repositories = azure(["acr", "repository", "list", "--name", registry], "registry_inventory")
    if not isinstance(repositories, list):
        raise PlatformFailure("invalid_registry_inventory")
    digest: str | None = None
    if repository in repositories:
        tags = azure(
            [
                "acr",
                "repository",
                "show-tags",
                "--name",
                registry,
                "--repository",
                repository,
                "--detail",
            ],
            "image_inventory",
        )
        if not isinstance(tags, list):
            raise PlatformFailure("invalid_image_inventory")
        for raw in tags:
            item = json_object(raw)
            if item.get("name") == tag:
                digest = text_field(item, "digest")
                break
    if digest is None:
        result = json_object(
            azure(
                [
                    "acr",
                    "build",
                    "--registry",
                    registry,
                    "--image",
                    f"{repository}:{tag}",
                    "--file",
                    str(root / f"services/{service}/Dockerfile"),
                    "--no-logs",
                    "--timeout",
                    "900",
                    str(root),
                ],
                "image_build",
                timeout=960,
            )
        )
        run_id = text_field(result, "runId")
        if result.get("status") != "Succeeded":
            raise PlatformFailure(f"image_build_failed_{run_id}")
        image = json_object(
            azure(
                [
                    "acr",
                    "repository",
                    "show",
                    "--name",
                    registry,
                    "--image",
                    f"{repository}:{tag}",
                ],
                "image_digest",
            )
        )
        digest = text_field(image, "digest")
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", digest):
        raise PlatformFailure("invalid_image_digest")
    set_environment(
        f"{service.upper()}_IMAGE",
        f"{env['AZURE_CONTAINER_REGISTRY_ENDPOINT']}/{repository}@{digest}",
    )
    event("image", "success", correlation, category=tag)


def temporary_jobs(env: dict[str, str]) -> dict[str, str]:
    raw = json_object(json.loads(env["PLATFORM_VERIFICATION_JOBS"]))
    if set(raw) != {"ingestion", "enrichment", "mcp", "migrations"}:
        raise PlatformFailure("verification_job_inventory")
    parent = env["MIGRATION_JOB_ID"].rsplit("/", 1)[0].lower() + "/verify-"
    jobs = {key: text_field(raw, key) for key in raw}
    if len(set(jobs.values())) != 4 or any(
        not job.lower().startswith(parent)
        or not re.fullmatch(r"[a-z0-9-]{1,25}", job[len(parent) :])
        or not job.endswith(f"-{name}")
        for name, job in jobs.items()
    ):
        raise PlatformFailure("unsafe_verification_job_scope")
    return jobs


def execute_job(job_id: str, correlation: str, *, arguments: list[str] | None = None) -> str:
    base = f"https://management.azure.com{job_id}"
    job = json_object(rest(f"{base}?api-version={API_VERSION}", "job_definition"))
    template = json_object(json_object(job["properties"])["template"])
    if any(template.get(key) not in (None, []) for key in ["initContainers", "volumes"]):
        raise PlatformFailure("unsupported_execution_template")
    containers = template.get("containers")
    if not isinstance(containers, list) or len(containers) != 1:
        raise PlatformFailure("invalid_execution_template")
    container = json_object(containers[0])
    values = container.get("env")
    if not isinstance(values, list):
        raise PlatformFailure("invalid_execution_environment")
    container["env"] = [
        item for item in values if json_object(item).get("name") != "PLATFORM_PROBE_RUN_ID"
    ] + [{"name": "PLATFORM_PROBE_RUN_ID", "value": correlation}]
    execution_container = {
        key: container[key]
        for key in ["name", "image", "command", "args", "resources", "env"]
        if key in container
    }
    if arguments is not None:
        execution_container["args"] = arguments
    execution = json_object(
        rest(
            f"{base}/start?api-version={API_VERSION}",
            "job_start",
            body={"containers": [execution_container]},
        )
    )
    name = text_field(execution, "name")
    if not re.fullmatch(r"[a-z0-9-]+", name):
        raise PlatformFailure("invalid_execution_name")
    deadline = time.monotonic() + 960
    while True:
        result = json_object(
            rest(f"{base}/executions/{name}?api-version={API_VERSION}", "execution_status")
        )
        status = text_field(json_object(result["properties"]), "status")
        if status == "Succeeded":
            event("execution", "success", correlation, category=name)
            return name
        if status not in ["Processing", "Running", "Unknown"] or time.monotonic() >= deadline:
            raise PlatformFailure(f"execution_failed_{name}")
        time.sleep(5)


def query(env: dict[str, str], expression: str) -> list[list[object]]:
    value = json_object(
        rest(
            f"https://api.loganalytics.azure.com/v1/workspaces/{env['LOG_ANALYTICS_WORKSPACE_ID']}/query",
            "telemetry_query",
            body={"query": expression},
            resource="https://api.loganalytics.io",
        )
    )
    tables = value.get("tables")
    if not isinstance(tables, list) or len(tables) != 1:
        raise PlatformFailure("invalid_query_tables")
    rows = json_object(tables[0]).get("rows")
    if not isinstance(rows, list) or any(not isinstance(row, list) for row in rows):
        raise PlatformFailure("invalid_query_rows")
    return rows


def verify(env: dict[str, str], correlation: str) -> None:
    jobs = temporary_jobs(env)
    executions = {name: execute_job(job, correlation) for name, job in sorted(jobs.items())}
    set_environment("PLATFORM_LAST_VERIFICATION_EXECUTIONS", json.dumps(executions, sort_keys=True))
    expression = (
        "AppEvents | where TimeGenerated > ago(1h) "
        "| where Name == 'newsloom.platform.probe' "
        f"and tostring(Properties.correlation_id) == '{correlation}' "
        "| summarize count() by tostring(Properties.workload), tostring(Properties.outcome)"
    )
    deadline = time.monotonic() + 600
    while True:
        rows = query(env, expression)
        observed = {
            str(row[0]) for row in rows if len(row) == 3 and row[1] == "success" and row[2] == 1
        }
        if observed == {"ingestion", "enrichment", "mcp"}:
            break
        if time.monotonic() >= deadline:
            raise PlatformFailure("authenticated_events_missing")
        time.sleep(10)
    expression = (
        "union isfuzzy=true ContainerAppConsoleLogs_CL, ContainerAppConsoleLogs "
        "| where TimeGenerated > ago(1h) "
        "| extend Message = tostring(column_ifexists('Log_s', column_ifexists('Log', ''))) "
        f"| where Message has '{correlation}' "
        "| extend Parsed = parse_json(Message) "
        "| summarize workloads=dcountif(tostring(Parsed.workload), "
        "tostring(Parsed.event) == 'platform_probe' and tostring(Parsed.outcome) == 'success'), "
        "leaks=countif(Message has 'NEWSLOOM_CONTENT_CANARY' "
        "or Message has 'NEWSLOOM_CREDENTIAL_CANARY')"
    )
    deadline = time.monotonic() + 600
    while True:
        rows = query(env, expression)
        if len(rows) == 1 and rows[0] == [4, 0]:
            break
        if rows and len(rows[0]) == 2 and rows[0][1] != 0:
            raise PlatformFailure("unsafe_console_diagnostics")
        if time.monotonic() >= deadline:
            raise PlatformFailure("console_evidence_missing")
        time.sleep(10)
    set_environment("PLATFORM_LAST_PROBE_RUN_ID", correlation)
    event("azure_verification", "success", correlation, checks=4)


def control(command: str, correlation: str, *, force: bool = False) -> None:
    env = environment()
    if command == "build":
        build(env, correlation)
    elif command == "build-ingestion":
        build(env, correlation, ingestion=True)
    elif command in ("execute-ingestion", "calibrate-ingestion", "read-ingestion"):
        reading = command == "read-ingestion"
        arguments = (
            ["ingestion-status"]
            if reading
            else ["calibrate"]
            if command == "calibrate-ingestion"
            else ["run", "--force"]
            if force
            else ["run"]
        )
        name = execute_job(
            env["MIGRATION_JOB_ID" if reading else "INGESTION_JOB_ID"],
            correlation,
            arguments=arguments,
        )
        prefix = (
            "INGESTION_READBACK"
            if reading
            else "INGESTION_CALIBRATION"
            if command == "calibrate-ingestion"
            else "INGESTION"
        )
        set_environment(f"{prefix}_LAST_EXECUTION", name)
        set_environment(f"{prefix}_LAST_RUN_ID", correlation)
    elif command == "execute":
        name = execute_job(env["MIGRATION_JOB_ID"], correlation)
        set_environment("MIGRATION_LAST_EXECUTION", name)
    elif command == "verify":
        verify(env, correlation)
    else:
        raise PlatformFailure("unknown_operator_action")
