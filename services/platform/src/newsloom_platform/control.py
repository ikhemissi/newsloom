"""Operator actions used by azd hooks; never provisions resources directly."""

import hashlib
import json
import math
import re
import shlex
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Literal

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
        if raw and (
            raw.startswith(("packages/", "services/"))
            or raw in ("config/feeds.json", "config/categories.json", "config/mcp-evaluation.json")
        ):
            paths.add(Path(raw))
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(str(path).encode() + b"\0" + (root / path).read_bytes() + b"\0")
    return digest.hexdigest()


def build(
    env: dict[str, str],
    correlation: str,
    *,
    service: Literal["platform", "ingestion", "enrichment", "mcp"] = "platform",
) -> None:
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


def verify_mcp(env: dict[str, str], correlation: str) -> None:
    from newsloom_platform.config import RuntimeConfig

    config = RuntimeConfig.from_environment(env)
    arguments = [
        "/app/.venv/bin/newsloom-mcp",
        "verify-access",
        "--generation-deployment",
        config.enrichment_deployment,
        "--screening-deployment",
        config.screening_deployment,
    ]
    if env.get("MCP_EVALUATION_RUN_ID"):
        arguments.extend(["--evaluation-run-id", env["MCP_EVALUATION_RUN_ID"]])
    output = run(
        [
            "az",
            "containerapp",
            "exec",
            "--name",
            env["MCP_APP_NAME"],
            "--resource-group",
            env["AZURE_RESOURCE_GROUP"],
            "--container",
            "mcp",
            "--command",
            shlex.join(arguments),
            "--only-show-errors",
        ],
        "mcp_replica_verification",
        timeout=240,
    )
    reports = []
    for line in output.splitlines():
        if not line.startswith("{"):
            continue
        try:
            record: object = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict) and record.get("event") == "mcp_access_verification":
            reports.append(record)
        if (
            isinstance(record, dict)
            and record.get("event") == "mcp_service"
            and record.get("outcome") == "failure"
        ):
            category = record.get("category")
            if isinstance(category, str) and (
                re.fullmatch(r"verification_[a-z_]{1,60}", category)
                or category
                in {
                    "ClientAuthenticationError",
                    "TimeoutError",
                    "OperationalError",
                    "ConnectError",
                    "ReadTimeout",
                    "invalid_verification_deployment",
                    "evaluation_schema_still_present",
                }
            ):
                raise PlatformFailure("mcp_access_failed_" + category)
    if len(reports) != 1 or reports[0].get("outcome") != "success":
        raise PlatformFailure("mcp_access_verification_missing")
    counts = json_object(reports[0].get("counts"))
    expected = {
        "tool_checks": 5,
        "database_denials": 10,
        "embedding_dimensions": 1536,
        "model_denials": 2,
        "anonymous_denials": 1,
        "wrong_resource_denials": 1,
        "app_only_denials": 3,
        "cleanup_checks": int(bool(env.get("MCP_EVALUATION_RUN_ID"))),
    }
    if set(counts) != {*expected, "news", "recent_ids"} or any(
        isinstance(value, bool) or not isinstance(value, int) for value in counts.values()
    ):
        raise PlatformFailure("invalid_mcp_access_report")
    if any(counts.get(key) != value for key, value in expected.items()):
        raise PlatformFailure("incomplete_mcp_access_verification")
    news, recent = counts["news"], counts["recent_ids"]
    if (
        not isinstance(news, int)
        or not isinstance(recent, int)
        or news < 1
        or recent != min(news, 5)
    ):
        raise PlatformFailure("invalid_mcp_access_report")
    set_environment("MCP_ACCESS_LAST_RUN_ID", correlation)
    set_environment("MCP_ACCESS_LAST_COUNTS", json.dumps(counts, sort_keys=True))
    event(
        "mcp_workload_verification",
        "success",
        correlation,
        checks=5,
        counts={key: value for key, value in counts.items() if isinstance(value, int)},
    )


def evaluate_mcp(env: dict[str, str], correlation: str) -> None:
    from newsloom_core.retrieval_fixtures import fixture_revision, load_fixtures

    from newsloom_platform.mcp_evaluation import evaluation_schema

    evaluation_schema(correlation)
    fixtures = load_fixtures()
    expected_cases = {case.id: case for case in fixtures.queries}
    corpus_ids = {item.id for item in fixtures.corpus}
    set_environment("MCP_EVALUATION_RUN_ID", correlation)
    try:
        execute_job(env["MIGRATION_JOB_ID"], correlation, arguments=["mcp-eval-prepare"])
        output = run(
            [
                "az",
                "containerapp",
                "exec",
                "--name",
                env["MCP_APP_NAME"],
                "--resource-group",
                env["AZURE_RESOURCE_GROUP"],
                "--container",
                "mcp",
                "--command",
                f"/app/.venv/bin/newsloom-mcp evaluate --evaluation-run-id {correlation}",
                "--only-show-errors",
            ],
            "mcp_replica_evaluation",
            timeout=1200,
        )
        records = []
        for line in output.splitlines():
            if not line.startswith("{"):
                continue
            try:
                record: object = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict) and record.get("correlation_id") == correlation:
                records.append(record)
        summaries = [record for record in records if record.get("event") == "mcp_evaluation"]
        cases = [record for record in records if record.get("event") == "mcp_evaluation_case"]
        if len(summaries) != 1 or len(cases) != 20:
            raise PlatformFailure("incomplete_mcp_replica_evaluation")
        report = json_object(summaries[0].get("counts"))
        if (
            report.get("passed") != 1
            or report.get("filtered_cases") != 10
            or report.get("unfiltered_cases") != 10
            or report.get("filter_violations") != 0
            or report.get("errors") != 0
        ):
            raise PlatformFailure("mcp_retrieval_gate_failed")
        safe_counts: dict[str, int | float | str] = {}
        for key in (
            "filtered_cases",
            "unfiltered_cases",
            "filtered_recall_at_5",
            "unfiltered_recall_at_5",
            "filter_violations",
            "errors",
        ):
            value = report.get(key)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                raise PlatformFailure("invalid_mcp_evaluation_report")
            safe_counts[key] = value
        if (
            min(
                float(safe_counts["filtered_recall_at_5"]),
                float(safe_counts["unfiltered_recall_at_5"]),
            )
            < 0.8
        ):
            raise PlatformFailure("mcp_retrieval_gate_failed")
        if (
            max(
                float(safe_counts["filtered_recall_at_5"]),
                float(safe_counts["unfiltered_recall_at_5"]),
            )
            > 1
        ):
            raise PlatformFailure("invalid_mcp_evaluation_report")
        revision = report.get("fixture_revision")
        if revision != fixture_revision():
            raise PlatformFailure("invalid_mcp_evaluation_report")
        safe_counts["fixture_revision"] = revision
        safe_cases = []
        observed_totals = {"filtered": 0.0, "unfiltered": 0.0}
        for record in cases:
            case_id = record.get("category")
            if not isinstance(case_id, str) or not re.fullmatch(r"[uf][0-9]{2}", case_id):
                raise PlatformFailure("invalid_mcp_case_report")
            counts = json_object(record.get("counts"))
            safe_case: dict[str, int | float | str] = {}
            for key in ("group", "relevant", "retrieved", "similarities", "recall_at_5", "error"):
                value = counts.get(key)
                if key == "group" and value not in ("filtered", "unfiltered"):
                    raise PlatformFailure("invalid_mcp_case_report")
                if key in ("relevant", "retrieved") and (
                    not isinstance(value, str)
                    or not re.fullmatch(r"(?:d[0-9]{2}(?:,d[0-9]{2})*)?", value)
                ):
                    raise PlatformFailure("invalid_mcp_case_report")
                if key == "similarities" and (
                    not isinstance(value, str)
                    or not re.fullmatch(r"(?:-?[0-9]+\.[0-9]{6}(?:,-?[0-9]+\.[0-9]{6})*)?", value)
                ):
                    raise PlatformFailure("invalid_mcp_case_report")
                if key == "error" and (
                    not isinstance(value, str) or not re.fullmatch(r"[a-z0-9_]{0,80}", value)
                ):
                    raise PlatformFailure("invalid_mcp_case_report")
                if key == "recall_at_5" and (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not 0 <= value <= 1
                ):
                    raise PlatformFailure("invalid_mcp_case_report")
                if not isinstance(value, (str, int, float)):
                    raise PlatformFailure("invalid_mcp_case_report")
                safe_case[key] = value
            case = expected_cases.get(case_id)
            observed = counts["retrieved"]
            similarities = counts["similarities"]
            recall = counts["recall_at_5"]
            if (
                case is None
                or counts["group"] != case.group
                or counts["relevant"] != ",".join(case.relevant)
                or counts["error"]
                or not isinstance(observed, str)
                or not isinstance(similarities, str)
                or not isinstance(recall, (int, float))
            ):
                raise PlatformFailure("invalid_mcp_case_report")
            retrieved = observed.split(",") if observed else []
            scores = [float(value) for value in similarities.split(",")] if similarities else []
            expected_recall = len(set(retrieved) & set(case.relevant)) / len(case.relevant)
            if (
                len(retrieved) > 5
                or len(set(retrieved)) != len(retrieved)
                or not set(retrieved) <= corpus_ids
                or len(scores) != len(retrieved)
                or any(not math.isfinite(score) or not -1 <= score <= 1 for score in scores)
                or not math.isclose(recall, expected_recall, abs_tol=1e-12)
            ):
                raise PlatformFailure("invalid_mcp_case_report")
            observed_totals[case.group] += recall
            safe_cases.append({"id": case_id, "counts": safe_case})
        expected = {f"{prefix}{index:02}" for prefix in ("u", "f") for index in range(1, 11)}
        if {str(record["id"]) for record in safe_cases} != expected:
            raise PlatformFailure("incomplete_mcp_replica_evaluation")
        if any(
            not math.isclose(total / 10, float(safe_counts[f"{group}_recall_at_5"]), abs_tol=1e-12)
            for group, total in observed_totals.items()
        ):
            raise PlatformFailure("invalid_mcp_evaluation_report")
        if not re.fullmatch(r"[a-z0-9-]+", env["AZURE_ENV_NAME"]):
            raise PlatformFailure("invalid_environment_name")
        path = Path(".azure") / env["AZURE_ENV_NAME"] / f"mcp-evaluation-{correlation}.json"
        run(["git", "check-ignore", str(path)], "private_evaluation_path")
        with path.open("x", encoding="utf-8") as output_file:
            json.dump(
                {"summary": safe_counts, "cases": safe_cases},
                output_file,
                indent=2,
                allow_nan=False,
            )
            output_file.write("\n")
        path.chmod(0o600)
    finally:
        execute_job(env["MIGRATION_JOB_ID"], correlation, arguments=["mcp-eval-cleanup"])
    event(
        "mcp_retrieval_evaluation",
        "success",
        correlation,
        checks=20,
        counts={"filtered_cases": 10, "unfiltered_cases": 10, "filter_violations": 0, "errors": 0},
    )


def control(command: str, correlation: str, *, force: bool = False, limit: int = 25) -> None:
    env = environment()
    if command == "build":
        build(env, correlation)
    elif command == "build-ingestion":
        build(env, correlation, service="ingestion")
    elif command == "build-enrichment":
        build(env, correlation, service="enrichment")
    elif command == "build-mcp":
        build(env, correlation, service="mcp")
    elif command == "verify-mcp":
        verify_mcp(env, correlation)
    elif command == "prepare-mcp-identity":
        from newsloom_platform.mcp_identity import prepare

        prepare(env, correlation)
    elif command == "evaluate-mcp":
        evaluate_mcp(env, correlation)
    elif command in ("prepare-mcp-evaluation", "cleanup-mcp-evaluation"):
        from newsloom_platform.mcp_evaluation import evaluation_schema

        preparing = command == "prepare-mcp-evaluation"
        run_id = correlation if preparing else env["MCP_EVALUATION_RUN_ID"]
        evaluation_schema(run_id)
        if preparing:
            set_environment("MCP_EVALUATION_RUN_ID", run_id)
        name = execute_job(
            env["MIGRATION_JOB_ID"],
            run_id,
            arguments=["mcp-eval-prepare" if preparing else "mcp-eval-cleanup"],
        )
        set_environment("MCP_EVALUATION_ADMIN_LAST_EXECUTION", name)
    elif command in (
        "execute-enrichment",
        "evaluate-enrichment",
        "read-enrichment",
        "verify-enrichment",
    ):
        if isinstance(limit, bool) or not 1 <= limit <= 25:
            raise PlatformFailure("invalid_enrichment_limit")
        reading = command == "read-enrichment"
        evaluating = command == "evaluate-enrichment"
        verifying = command == "verify-enrichment"
        arguments = (
            ["enrichment-status"]
            if reading
            else ["evaluate"]
            if evaluating
            else ["verify-access"]
            if verifying
            else ["run", "--limit", str(limit)]
        )
        name = execute_job(
            env["MIGRATION_JOB_ID" if reading else "ENRICHMENT_JOB_ID"],
            correlation,
            arguments=arguments,
        )
        prefix = (
            "ENRICHMENT_READBACK"
            if reading
            else "ENRICHMENT_EVALUATION"
            if evaluating
            else "ENRICHMENT_VERIFICATION"
            if verifying
            else "ENRICHMENT"
        )
        set_environment(f"{prefix}_LAST_EXECUTION", name)
        set_environment(f"{prefix}_LAST_RUN_ID", correlation)
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
