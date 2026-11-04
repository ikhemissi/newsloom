"""Run frozen authored controller controls; emit only content-free outcomes."""

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTROLS = {
    "unknown_tool": (
        "tests/test_agent_research_generation.py"
        "::test_malformed_plans_fail_without_repair_generation",
    ),
    "changed_endpoint": (
        "tests/test_agent_delegation.py"
        "::test_sdk_redirects_cannot_move_the_mcp_authorization_channel",
    ),
    "scope_broadening": (
        "tests/test_agent_research.py"
        "::test_whole_plan_filter_relaxation_does_not_execute_earlier_legal_call",
    ),
    "retrieved_instruction": (
        "tests/test_agent_research_generation.py"
        "::test_actual_wire_schema_uses_scope_not_untrusted_context",
        "tests/test_agent_research_privacy.py"
        "::test_real_research_http_content_canaries_cover_success_faults_and_overload",
    ),
}


def main() -> int:
    deadline = time.monotonic() + 120
    results: list[dict[str, object]] = []
    for name, nodes in CONTROLS.items():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            print('{"outcome":"failure","category":"baseline_local_controls_deadline"}')
            return 1
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", *nodes],
                cwd=ROOT,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=remaining,
                check=False,
            )
        except OSError, subprocess.TimeoutExpired:
            print('{"outcome":"failure","category":"baseline_local_controls_unavailable"}')
            return 1
        results.append(
            {
                "control_id": name,
                "modality": "offline_scripted_controller",
                "passed": result.returncode == 0,
                "test_source_sha256": hashlib.sha256(
                    json.dumps(
                        {
                            node.split("::", 1)[0]: hashlib.sha256(
                                (ROOT / node.split("::", 1)[0]).read_bytes()
                            ).hexdigest()
                            for node in nodes
                        },
                        sort_keys=True,
                    ).encode()
                ).hexdigest(),
            }
        )
    passed = all(value["passed"] for value in results)
    print(
        json.dumps(
            {
                "protocol": "baseline-local-controls-v1",
                "outcome": "passed" if passed else "failed",
                "controls": results,
                "model_calls": 0,
                "live_indirect_attack_claim": False,
            },
            sort_keys=True,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
