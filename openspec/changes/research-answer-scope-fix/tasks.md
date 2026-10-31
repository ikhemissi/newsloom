# Tasks

The user approved this narrow agent correctness scope and agent-only redeploy.
Keep the existing USD 100 allowance and record all usage, including failed
diagnostics. No baseline request or score is silently repaired/replayed.

## 1. Trusted synthesis scope

- [x] 1.1 Implement a typed application-owned synthesis scope and pass it explicitly through the controller/model interface. Bind coverage and missing IDs in the final schema while preserving independent validation, request limits and no-match behavior. Verify actual SDK/schema and controller tests for discovery, complete/partial/none selection, untrusted context, wrong coverage, duplicate/foreign missing IDs and no repair; update the agent runbook.
- [x] 1.2 Run the primary local gate, six package builds, types/lint/OpenSpec and documentation checks. Record actual passed/skipped counts, preserve production locks and unrelated customizations, and verify no cloud credentials or inference are needed for ordinary checks.

## 2. Agent-only deployment and measured verification

Local 1.1 evidence: 148 focused generation/controller/A2A/capture tests pass,
including actual pinned SDK schemas, all four coverage modes, forged content
controls and provider outputs with wrong coverage, foreign or duplicate missing
IDs. Strict application types pass across 145 source/test files. The model
interface and every resolved direct/scripted caller use the typed trusted
scope. No returned value is repaired and no extra generation is admitted.
The agent runbook distinguishes this local proof from pending deployment/live
acceptance. Production manifests/lock remain unchanged.

Local 1.2 evidence: the PostgreSQL-enabled primary gate passes 477 evaluator
tests and 1,616 application tests, with one intentionally excluded live-publisher
test and no PostgreSQL skips. Types pass across 52 evaluator and 145 application
source/test files; lint, formatting, runtime isolation, identifiers, feed
validation, OpenSpec and all existing Terraform validations/mock tests pass.
All six packages build. Five owning documentation files have 70 valid local
links/anchors and 15 syntax-checked shell blocks. Pylance verifies all four
resolved generator synthesis callers are signature-compatible. The owned
loopback PG18 helper was stopped/removed. These ordinary tests require no
cloud credentials or inference.

The built image source is
`994707f93566db4f67d8d79aff1116ace2d763776d3775a41de835568a4dc60c`.
The exact reviewed native agent plan is
`975a610ceeaa1b8178fe265156d3f0618b3d2bc764053edbae11a62f477bc19b`.
It admits one update with only container image and runtime-revision env value
changed: no creates, destroys, role/model/capacity or other configuration change.
This reviewed preview preceded the successful owning apply recorded below.

- [x] 2.1 Build the new immutable agent image with the existing owning command, review the exact agent-only azd preview and verify only image/revision updates with unchanged identities/configuration and no creates/destroys or new resource/model/grant. Apply only that reviewed scope and independently verify its exact deployed image/configuration; retain the old accepted image and failed baseline evidence.
- [x] 2.2 Run one bounded same-user discovery verification against the new image with pre/post evidence fingerprints, validated streaming/task parity, correct coverage and observed usage. Verify selected/no-match compatibility locally, preserve privacy and failed costs, close owned helpers, and leave the full baseline/report gates open.

## 3. Source-bound delivery

Measured 2.1 evidence: the owning azd apply succeeded with zero additions, one
agent change and zero destroys. The first independent readback caught transient
rollout lag and remains a failed observation. A subsequent bounded status read
confirmed Succeeded/Running, matching image/revision and ready latest revision;
the complete owning verifier then passed configuration/image guards at source
`994707f93566db4f67d8d79aff1116ace2d763776d3775a41de835568a4dc60c`.
The new immutable image digest is
`7cac78479b9c3c755e527e4a4986015ecbb3e46610c721bfd53c23930868e337`.
The prior image and failed baseline receipts remain preserved; no unrelated
layer, identity, model, capacity or resource was provisioned.

The bounded post-deployment discovery verification expired at the user's
2026-10-31 11:15:30 UTC availability deadline while awaiting the first sign-in.
No new A2A discovery request or model generation was dispatched in that
verification; its consumed sign-in attempt remains counted. Callback servers
and the owned test database are closed/removed. Task 2.2 and source-bound
publication/CI remain unchecked. Do not extend the deadline or relabel local
schema tests as live coverage acceptance.

The user subsequently resumed verification with a new bounded attempt, keeping
the expired attempt and prior counters/cost exposure. The deployed image/
configuration was independently reverified at the same source before dispatch.
Both existing-client sign-ins succeeded. One discovery request completed with
supported outcome, one evidence item, two tool calls, four generation/usage
calls, 4,743 input tokens and 373 output tokens. Estimated chat cost is
USD 0.005759325; query-embedding exposure remains separately reserved at
USD 0.031064064 rather than described as measured. Actual pre/post item and
complete pool fingerprints matched the original constrained bindings.
The SDK validated streamed answer/completed-task parity and preserved the
signed-in user; final controller validation proves correct discovery coverage.
No article/answer/reason content was saved. Only the answer hash and receipt
remain; the answer was 844 bytes. Callback clients/processes closed normally.

This verifies the narrow coverage fix, not complete semantic quality, every
baseline case or an actual indirect-injection attack. Selected/no-match and
provider-violation compatibility remain separately grounded in the local
148-test selection and full primary gate. The whole baseline and report/UI
gates remain open. Source-bound implementation/status CI is still pending.

Implementation publication is verified at
`af108f171b60a757fbc3c18aaed335997a457aa9`, with passing
[exact-source primary CI](https://github.com/ikhemissi/newsloom/actions/runs/41197276231).
Only the scoped agent/contracts/tests/runbook/change artifacts were committed;
the active baseline and unrelated customization work remain preserved and
unstaged. This separate measured-status publication records live acceptance
after implementation CI, but its own exact-source CI is still pending.
Task 3.1 remains unchecked until both publication gates have passed.

- [ ] 3.1 Publish the implementation and measured evidence, preserving unrelated work; verify exact-source primary CI and separate measured-status publication/CI before completing this slice. Keep any unavailable acceptance unchecked and do not archive automatically.
