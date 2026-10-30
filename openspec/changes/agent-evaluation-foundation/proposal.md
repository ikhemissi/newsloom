# Proposal

## Why

The delivered research agent has focused acceptance evidence, but no reproducible
DeepEval-to-Foundry evaluation path. Before investing in a phase-wide quality
baseline, prove Python compatibility, secretless judging, honest cost accounting
and actual Foundry evaluation-report visibility.

## What Changes

- Deliver the first bounded part of [Step 2.3](../../../docs/prd-2.md#delivery-plan),
  preparing for [P2-C06](../../../docs/prd-2-capabilities.md#p2-c06-repeatable-agent-quality-and-azure-acceptance)
  without declaring that capability or Phase 2 complete.
- Add an operator-invoked evaluation pilot using two authored, precomputed
  question/evidence/answer cases: one supported answer and one deliberately
  unsupported answer. No production content or agent generation is needed.
- Prove DeepEval and the current Foundry evaluation SDK on supported Python
  3.15 in a separate, non-packaged evaluation-only uv project with its own lock
  and environment. Preserve the application lock and production dependency
  closures; keep evaluation libraries outside production installations.
- Score the cases with one explicitly configured DeepEval faithfulness metric
  using an existing Azure chat deployment and Entra authentication.
- Publish validated, explicitly labelled imported DeepEval scores through
  Foundry's native inline Python graders; verify case-level scores and lineage through
  both API readback and the actual Evaluations report. This adapter is a
  feasibility gate, not an already demonstrated integration.
- Use the explicitly approved native-Python replay protocol demonstrated by
  the user's live reference, rather than registering another catalog evaluator.
  New publication creates only an evaluation definition and its inline-data
  run. Keep existing grants and both failed catalog intents unchanged; no
  account-scoped grant, new resource, model or capacity is needed. The user's
  subsequent sample-first instruction permits scoring and uploading the existing
  two-case synthetic pilot within its unchanged budget before testing deletion.
  Test exact-owned deletion only after successful upload; Foundry Project Manager
  may be added for the selected operator on the existing evaluation project only
  if that upload succeeds and deletion then fails. Do not expand grant scope or
  treat this exception as lifecycle acceptance. Preserve historical unknown
  outcomes without replay or absence claims. Reference success is not Newsloom
  acceptance.
- The user's subsequent instruction after the real upload authorization failure
  explicitly permits adding Foundry Project Manager now, for the same operator
  on the existing evaluation project, before deletion testing. Permit only the
  provider-required exact definition GETs and one reviewed assignment addition.
  Retry publication of the retained scores without rescoring or replaying the
  failed run; preserve the original journal and deadline.
- The user's subsequent instruction permits testing both built-in roles at
  the retained Foundry account scope for the same human operator. Keep project
  and custom grants unchanged during this additive diagnostic test, record
  exact account assignments privately, then retry only the saved scores with
  the explicit evaluation-preview header. Do not claim these experimental
  account assignments are Terraform-owned before their exact-ID adoption.
- Bound all inference attempts, polling, retention and estimated spending;
  preserve missing usage, failures and ambiguous publication outcomes.
- Reconcile the subsequently approved CLI/manual evaluation data foundation
  into the owning Terraform layer by exact-ID import, preserving the working
  project-managed-identity storage connection and existing account/operator
  grants. Adopt the two unused diagnostic Application Insights grants before
  removing only those assignments through a separate reviewed Terraform plan.
  Keep accepted reports, deployed workloads and the other reference project
  untouched; failed experiment cleanup requires independent exact ownership
  and logical-absence evidence, not deletion replay or inferred backup erasure.
- Finish preservation with the explicitly approved, evidence-bound
  [final metadata reconciliation](design.md#4j-final-audited-preservation-reconciliation).
  Admit only the observed additional account endpoint descriptor on the
  existing Azure account hostname and the exactly reconstructed rolling
  PostgreSQL restore date. Treat verified policy-managed scanning side
  resources as outside direct evaluation IaC ownership, not orphan experiments.
  Preserve failed snapshots and all unrelated account, authority, workload,
  model and data checks; this permits neither blanket drift suppression nor
  changes to Defender. Retain the working evaluation storage.
- Limit cloud verification to the selected Newsloom resource group and its
  resources, the Newsloom database there, and the project's four app
  registrations. Inspect RG/resource-scoped assignments and project-owned custom
  role metadata only; do not collect broader inventories and filter afterward.
  Provision only a separately reviewed, minimally scoped Foundry evaluation
  foundation through an owning azd layer.
  Reuse the existing model account, adding project management and its required
  account identity in place; keep production workload identities, models,
  application behavior and original stored records unchanged. Reconcile
  continued pipeline publication only with evidence proving unchanged original
  fingerprints and explicitly identified additions.
- Add audited, source-bound reconciliation for the observed service-reported
  CostControls marker and append-only news growth within that verification
  boundary. Exclude global built-in role-definition checks rather than expanding
  their timestamp allowlist. Retain the original failed before/after evidence;
  new receipts must state the narrower scope, not claim wider preservation or
  replace the original failure with a success override.
- Admit only the separately approved first-project bookkeeping observed after
  the evaluation-layer apply: `associatedProjects` containing exactly the
  approved child project's name and `defaultProject` naming that same project.
  Bind this absent-to-owned-project transition and any verifier-only correction
  to the original source, baseline, reviewed/applied plan and failed readback.
  Preserve every other account check and the original receipts; do not reapply
  resources, replay verification executions or add a general metadata exception.
- Add the separately approved Foundry User assignment for the selected operator
  on the existing evaluation project only. This built-in role is broader than
  the custom evaluation role; retain the existing custom evaluation and
  account-scoped chat grants unchanged. Apply this one-assignment delta through
  the owning Terraform/azd layer and verify actual catalog authorization with
  bounded, exact-owned reads. Do not assign the role at account, RG or
  subscription scope, grant it to a managed identity, or infer working
  authorization from assignment readback alone. Preserve the expired lifecycle
  probe and its unknown remote outcome without replaying it or starting judging.
  The user separately permits only the exact built-in role-definition metadata
  reads required by the pinned AzureRM assignment resource; this is not
  permission for global role inventories or other out-of-RG checks.
  The subsequent instruction to proceed also admits only the disclosed
  refresh-state `null`-to-`[]` representations for the project's `identity_ids`,
  both custom roles' `not_data_actions`, and the corresponding existing
  custom-grant output. These do not authorize any additional resource mutation.

Prerequisites are the delivered Phase 1 and Steps 2.1-2.2, followed by review and
synchronization/archival of the completed `agent-research` change before this
slice is applied. Existing verified acceptance is referenced, not rerun merely
for archival.

Out of scope: the frozen phase-wide question set, calibrated quality thresholds,
native LLM-judge comparisons, deployed-agent quality acceptance, automated paid
CI, scheduled canaries, production traffic sampling, prompt/completion capture,
automatic optimization/deployment, new model deployments/capacity, web, memory,
UI work and a move to Foundry-hosted agents. These remain subsequent slices.
Cloud verification also excludes subscription-wide inventories, inherited
subscription/management-group grants, assignments outside the RG, global built-in
role definitions, subscription quota/catalog inventories and unrelated directory
objects. Local environment-context checks do not authorize those cloud reads.
The sole built-in-definition exception is the provider-required exact Foundry
User metadata read approved above, not a broader preservation check.

## Capabilities

### New Capabilities

- `agent-evaluation`: Reproducible, bounded agent-quality evaluation execution
  and Foundry-visible results, initially limited to a synthetic interoperability
  pilot with explicit provenance and preservation guarantees.

### Modified Capabilities

None. Existing telemetry, delegated access, runtime and Phase 1 acceptance
requirements remain unchanged.

## Impact

- A separately locked evaluation-only project, authored fixtures and focused
  tests; an explicit application-workspace exclusion without application-lock
  changes; cross-environment isolation checks and existing unpaid local/CI gates.
- A new evaluation-owned Terraform/azd boundary and existing platform preparation
  helpers only where needed for reviewed project configuration and outputs.
- One additional, explicitly approved project-scoped built-in role assignment
  after the custom-role catalog denial. Historical foundation/readback evidence
  remains unchanged; a separate source-bound permission-transition receipt must
  identify the exact new grant and observed authorization outcome.
- A bounded content-free preservation proof, using existing least-privileged
  verification first. The approved fallback is at most one verification-only
  execution under the existing migration identity, constrained to READ ONLY
  SQL and hashes/counts. It permits no migrations, schema/data writes, new grants,
  image deployment or use of that identity for evaluation publication.
- A future evaluation runbook plus owning PRD/ADR links and measured receipts.
  Planning creates only this change's artifacts, not implementation or delivery
  status updates.
- The last verified account had project management disabled and no Foundry
  project. The pinned provider supports projects on that account. The user
  selected reuse after being informed that disabling project management or
  removing the required account identity later would require replacement:
  those settings must remain enabled, and replacement is prohibited. Exact
  project identity/RBAC, regional operation, deployment reuse and data lifecycle
  still require the design's specific preflight. A new account/model requires
  a separate scope decision.
- Exact provisioning/grant changes and a finite pilot spending envelope require
  explicit approval before execution. Step 2.2's paid authorization is not
  inherited; no resource, role, inference, compatibility or result-visibility
  success is claimed by this proposal.
