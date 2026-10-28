# Tasks

The research prerequisite is archived and published as `d3483504aa673adc9b10031cd564b0916008d70f`,
with passing [exact-commit CI](https://github.com/ikhemissi/newsloom/actions/runs/40664742550).
The first dependency-isolation check found a blocker: DeepEval 4.3.2 requires
`click>=8,<8.4`, but the production agent and MCP closures use Click 8.5.0.
The candidate resolution downgraded both closures to Click 8.3.3, so the manifest,
lock and development environment were restored. The user selected a separate
evaluation-only Python 3.15 project/lock rather than a production downgrade.
The isolated environment, bounded runner, publication/recovery bridge,
exact-target cleanup and privacy guards pass 213 actual-library/offline
tests, lint, formatting and strict types on Python 3.15.1. The application lock
and all six production closures remain unchanged; isolated agent startup and
six-package builds pass. Mocked wire evidence is documented in the
[evaluation runbook](../../../docs/agent-evaluation.md), not Azure/report acceptance.
Fresh read-only workload/directory/model/grant preservation now passes after an
earlier interrupted preflight. Native account/operator inventory and an
independent count/hash-only stored-record baseline also pass. Evaluation
API/retention feasibility and exact grants remain pending; no evaluation
provisioning or paid evaluation is complete.
Apply the [design](design.md) and
[evaluation contract](specs/agent-evaluation/spec.md). This is Step 2.3's
interoperability foundation, not its frozen quality baseline.

The user selected reuse of the existing account after reviewing the lasting
project-management/identity settings. That planning choice is not approval for
an unreviewed deployment, new roles, retention policy or paid run. The proposed
USD 1/12-attempt pilot envelope requires task 6.1's explicit execution approval.

## 1. Prerequisite and read-only foundation preflight

- [x] 1.1 Review the completed `agent-research` change and its existing local/Azure and exact-SHA implementation/status evidence; synchronize/archive it through the owning workflow before applying this slice. Verify the delivered research contracts, updated local links and archival publication CI without repeating paid research acceptance merely for archival.
- [ ] 1.2 Inspect the retained `dev` account/project inventory, project-management/identity state, regional evaluation support, existing chat deployment/version/throughput/quota, operator data-plane access and evaluation API/retention contracts. Record content-free before-baselines for application images/configuration, workload identities/grants, all models, schedules and stored-record fingerprints using existing authorized verification paths. Verify that one in-place account prerequisite update and one child project can satisfy the chosen design without replacement, new capacity or broader production access; report blockers before cloud writes.

## 2. Locked library compatibility and production isolation

- [x] 2.1 Add the non-packaged `tools/agent-evaluation/` Python 3.15 uv project with its own manifest, lock, environment and pinned evaluation/checking dependencies; explicitly exclude it from the application workspace. Keep root development dependencies, service manifests, the application lock and all six production dependency closures unchanged. Verify actual imports in the evaluation environment, isolated production agent startup with evaluation libraries absent and all six existing package builds. Document distinct locked commands in the README and a new evaluation runbook; stop on incompatibility or cross-environment leakage rather than downgrading Python or production dependencies.
- [x] 2.2 Add focused actual-library tests under the evaluation project using controlled local transports for the selected metric's asynchronous/schema contract and the Projects SDK's Entra evaluation endpoints, serialization and error handling. Prove real metric/SDK execution performs no paid network work, emits no vendor telemetry and does not inherit key credentials, external provider defaults or application-environment imports. Verify test discovery/plugins cannot initialize DeepEval before privacy opt-outs, and test that the conflicting evaluation dependency cannot alter the application lock or production closures. Record verified versions and wire shapes in the evaluation runbook before Azure execution.

## 3. Bounded synthetic runner and Foundry publication

- [x] 3.1 Implement the strict two-case authored fixtures under repository `config/` and the operator CLI under `tools/agent-evaluation/agent_evaluation/`, invoked only through its locked environment. Add the fixed-endpoint asynchronous judge adapter, shared attempt/byte/output/deadline/cost reservations and usage-completeness reporting. Exercise the real faithfulness metric against scripted responses; test input/configuration digests, unknown fields, internal extra calls, exact-boundary/one-over limits, throttling, rejected redirects/fallbacks, disabled retries, failures and cancellation without resetting reservations. Document the proposed finite envelope, diagnostic labels and the absence of an agent-quality claim.
- [x] 3.2 Implement strict result/lineage validation, the labelled imported-score evaluator, explicit dataset/evaluator/evaluation/run submission and complete paginated readback. Test exact score/case equality, preserved synthetic explanations, missing/duplicate/stale rows, boolean/nonfinite/range rejection, sandbox error placeholders, partial runs, bounded polling and ambiguous-mutation recovery with zero repeated inference. Document how to locate the returned report and distinguish imported scores from native judges.
- [x] 3.3 Implement operator-owned exact-target retention/cleanup and safe recovery records for the selected project, datasets and evaluations. Add forced-instrumentation/content/credential canaries across imports, judging, publication, failure, cancellation, diagnostics and filesystem caches; verify only approved Azure requests and intentional synthetic artifacts occur. Test foreign/missing ownership rejection and unknown deletion outcomes; document the proposed 30-day manual retention window, service limitations and the absence of automatic expiry or production-content capture.

## 4. Owning Terraform and azd boundaries

- [x] 4.1 Add in-place project management and the required account identity/outputs to the existing application root, preserving `prevent_destroy`, local-auth denial and all existing account/model/workload settings. Add the evaluation-owned project/grants layer, its application dependency and retained-environment preparation/outputs using the pinned providers. Add mocked-provider and preparation tests proving no account replacement, new model, unrelated resource or production grant expansion; document the lasting parent configuration and safe rollback.
- [ ] 4.2 Add exact native-plan and deployed-readback verification for both owning layers, including principal/scope/operation inventory, unexpected service-added assignments, key-auth state, retained model/version/capacity/endpoint and existing runtime/data boundaries. Test replacement, foreign account/project, unsupported scopes, drift and missing evidence failures; wire the new layer into existing validation/CI and document preview/review commands without storing deployment identifiers.

Local 4.1 evidence: 183 focused platform regressions, including 42 new
preparation/boundary tests, pass, as do 12 evaluation-layer and three application-root Terraform
mock runs, strict types, lint, formatting, platform packaging and CLI help.
These verify the declared boundaries and destruction guards, not native update
actions or working catalog authorization. See the
[owning-layer runbook](../../../docs/agent-evaluation.md#owning-infrastructure-boundary).
Tasks 1.2, 4.2 and the Azure acceptance gates remain pending; no cloud writes occurred.

## 5. Complete local integration gate

- [ ] 5.1 Wire the isolated evaluation project's locked lint, strict type and scripted-provider tests into the existing primary check and CI without merging environments or requiring Azure credentials/paid inference. Run focused tests first, then the PostgreSQL-enabled `bash scripts/check.sh` and six-package `uv build --all-packages`, including new Terraform mocks, unchanged application-lock/closure assertions, production package isolation and privacy checks. Validate documentation links/anchors, command syntax and identifier/whitespace guards. Bind the evaluation manifest/lock/code and fixture/configuration inputs to evaluator provenance, separately from the unchanged deployed agent's accepted image/source; do not build or redeploy the agent solely for this evaluation slice.

## 6. Approved deployment and actual Foundry acceptance

- [ ] 6.1 Refresh prices, throughput/quota and read-only preservation baselines; present both exact owning previews, every proposed principal/grant, the verified retention/deletion policy and the cumulative pilot envelope for explicit approval. Include finite publication mutation/read-only polling limits, conservative token-cost reservations, shared deadlines and all prior attempt/unknown-usage reservations. Record approval before applying resources, granting roles or running paid evaluation; expand neither scope nor budget silently.
- [ ] 6.2 Apply only the reviewed in-place application prerequisite plan, verify unchanged account/endpoints/models/workload authority, then apply the reviewed evaluation-layer plan through the existing azd environment. Independently verify the project, identities, exact grants, local-auth denial, deployment visibility and stable runtime settings before dataset upload or judging. Keep required parent identity/project-management settings enabled on failure; no account recreation or production image deployment is permitted.
- [ ] 6.3 Use the approved bounded metadata-only probe to verify the actual evaluation publication/reconciliation and exact-owned deletion path, including observed service retention limitations. Verify probe removal without affecting foreign assets; retain safe recovery references for uncertain outcomes and block content upload if the approved lifecycle cannot be demonstrated.
- [ ] 6.4 Execute the two-case real DeepEval pilot once within the approved shared envelope, then publish its validated original scores without further judge calls. Retrieve every actual Foundry result page and independently match case IDs, scores, metric origin, explanations and source/configuration lineage. Open the returned Evaluations report and verify actual case-level visibility; record measured usage/cost exclusions and any expected poor-answer score without turning it into an execution error or rerunning until pass.
- [ ] 6.5 Verify final application image/configuration, workload identities/grants, retained account/model/version/capacity/endpoint, schedules/history and independently obtained stored-record fingerprints against the before-baselines. Confirm no production content, new model/capacity, broader application access, unintended logs/caches or orphan probe assets; close owned local clients/helpers and record any retained exact recovery target. Missing Foundry UI/API parity or preservation proof leaves acceptance unchecked.

## 7. Source-bound publication and honest status

- [ ] 7.1 Update the evaluation runbook with actual compatibility, source/configuration, owning preview/apply, API/report visibility, retention, privacy, budget and preservation evidence; update only directly owning ADR/PRD links. Publish the verified implementation and wait for exact-commit primary CI, preserving unrelated customization edits. Keep Step 2.3/P2-C06 incomplete and distinguish the evaluator source from the unchanged agent image provenance.
- [ ] 7.2 Publish a separate measured evidence/status receipt after implementation CI passes, including exact report references kept private where required, actual counts, incomplete-usage reservations, cleanup and evidence limitations. Wait for that receipt's exact-SHA CI before completing delivery acceptance; no hypothetical or failed verification may become a passed task.
- [ ] 7.3 After the evidence/status CI passes, mark only this foundation delivery's completed gates and publish its completion ledger with final exact-head CI. Verify all foundation tasks have evidence while the frozen baseline/calibration, candidate comparison and online-monitoring slices remain pending; do not synchronize or archive this change automatically.

## Workflow follow-up

- Review the completed foundation evidence before synchronizing/archiving this
  change, then verify the published contract and updated documentation links.
- Propose the next small Step 2.3 slice for frozen questions, calibrated judges
  and the Foundry-visible quality baseline; design private online monitoring
  and paid automation separately without assuming production-content consent.
