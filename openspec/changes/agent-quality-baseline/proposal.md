# Proposal

## Why

The delivered evaluation foundation proves score transport, not research quality:
its two answers were precomputed. Establish a frozen, evidence-bound baseline
of the actual signed-in research agent before comparing candidates or designing
production monitoring.

## What Changes

- Deliver the next bounded part of [Step 2.3](../../../docs/prd-2.md#delivery-plan)
  toward [P2-C06](../../../docs/prd-2-capabilities.md#p2-c06-repeatable-agent-quality-and-azure-acceptance).
  Prerequisites are delivered research and the archived evaluation foundation
  at `95570c48fa7bf7a16e2778be7d49d938a2fd9ea5`, with passing
  [archival CI](https://github.com/ikhemissi/newsloom/actions/runs/41097873031).
- Freeze a small versioned suite: 12 live cases spanning selected-item
  explanation/comparison, discovery/filters, preferences, limited/no evidence
  and authorization denial; eight authored judge controls; separate offline
  indirect-injection and exact tool-policy controls. Label execution modality
  so local injection tests cannot masquerade as attacks exercised in Azure.
- Invoke the existing ACA/A2A agent through the existing public-client PKCE
  and validated streaming/task-readback contract. Use its actual answers and
  metered receipts, not replacement answers or a direct-model substitute.
  Bind private selected-item IDs, summary fingerprints, expected facts,
  applicability and pass criteria before any baseline generation.
- Use the isolated DeepEval faithfulness adapter only after its fixed authored
  calibration controls pass. Combine semantic support with deterministic
  citation/request-contract checks and exact offline tool-policy assertions.
  Retain failures without answer repair, judge reruns or threshold tuning.
- Apply the user's selected privacy design: approved stored summaries and
  generated answers may enter the existing Azure judge transiently, but saved
  receipts and Foundry rows contain only opaque case/metric IDs, finite scores,
  hashes, fixed outcome categories, timings and usage. Never persist/upload
  production-derived article text, answers, prompts, preferences or judge
  explanations. Versioned authored controls/templates remain explicit fixtures.
- Add a separately versioned metadata-only publication protocol, preserving
  exact canonical-string scores and complete per-metric denominators. Keep
  the two-case authored pilot, its commands, approvals and retained reports
  unchanged. Do not reinterpret old journals as baseline runs.
- Propose a fresh USD 10 combined model-admission ceiling, 12 live request
  slots, 80 judge attempts, six publication creates and 180 publication reads.
  Include conservative MCP query-embedding exposure and its retained bounded
  retries, not just chat usage. Run all stages
  within one three-hour execution window. Prices, retained deployments,
  conservative chat/embedding reservations, privacy/retention and exact scopes require a
  separate explicit execution approval after local verification; none is
  granted by this proposal or inherited from the old pilot.

Out of scope: candidate modifications/comparisons, automatic optimization,
online sampling or trace harvesting, new Foundry-hosted agents, new models,
capacity, grants, resources, dependencies or production data writes; web,
memory and PRD-3. This baseline does not alone declare Phase 2 complete.
Pause after the entire PRD-2 delivery, before PRD-3, as already recorded there.

## Capabilities

### New Capabilities

- `agent-quality-baseline`: Frozen, calibrated, bounded actual-agent quality
  measurement with explicit local/live coverage, provenance and acceptance.

### Modified Capabilities

- `agent-evaluation`: Extend its data-handling requirement only for explicitly
  approved transient baseline judging and metadata-only baseline artifacts.
  Preserve authored-only pilot inputs and all existing privacy scenarios.

## Impact

- Operator capture/orchestration under the existing root environment and
  separately locked evaluator project, using typed bounded in-memory IPC.
  Existing `ResearchInvocation.text`, complete task readback and usage receipts
  are reusable; the current verification CLI intentionally returns counts only.
  No environment mixing or production dependency-closure change is needed.
- A new frozen manifest/oracle format, scorer applicability, calibration gate,
  strict content-free result schema and exact metadata-only publication tests.
  Root-workspace A2A/MCP capture must prove existing-consent same-user access
  locally before any paid request; missing evidence is a blocker, not a reason
  to broaden grants or introduce production tracing.
- Existing Entra identities, accepted agent image and retained Foundry
  model/project/storage are reused. Fresh readiness within the established
  RG/database/project-app boundary remains required; no subscription quota or
  catalog inventory is authorized. No new availability or minimum-RBAC claim
  follows from previous successful publication.
- No production deployment is intended. Verify existing azd-owned configuration
  through exact no-change previews and scoped readback; unexpected necessary
  application/infrastructure changes require a separate reviewed scope decision.
- Implementation, measured Azure/report acceptance, preservation and separate
  implementation/status CI remain future unchecked tasks. Planning does not
  approve a paid run, new capture session, deployment or retention extension.
