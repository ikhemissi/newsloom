# Tasks

Implementation is underway. Unchecked tasks remain acceptance obligations,
not evidence. See [design](design.md) and the
[browser contract](specs/browser-research-ui/spec.md).
The existing evaluation ledger and consumed runs stay unchanged.

## 1. Approved sequencing and bounded SDK setup

- [x] 1.1 Update PRD-2/PRD-3 and relevant capabilities/ADRs with the explicitly approved early-access exception, React/MSAL/A2A/ACA direction, progress-then-final-answer semantics and subsequent feed/search slice; verify local links, capability assignments and that PRD-2 quality/full PRD-3 acceptance remain pending.
- [x] 1.2 Add the minimal `services/web` npm workspace and exact dependency locks, using the existing Node 24 CI runtime; within the 45-minute compatibility bound prove official A2A 1.0 discovery, strict JSON-RPC headers/body, streaming, GetTask and AbortSignal hooks against a local authored transport. Verify `npm ci`, workspace typecheck/build and contract tests; record the ADR comparison and pause on a concrete incompatibility rather than add a bridge.

## 2. Browser-ready agent without changed research authority

- [x] 2.1 Implement exact-origin CORS/preflight outside agent admission/authentication and document it in the agent runbook; verify allowed/denied/duplicate origins, methods, headers, max age, Vary, actual success/error/SSE headers and zero auth/capacity/downstream work for preflight in focused agent-serving tests.
- [x] 2.2 Wire normalized origins through owning agent preparation, Terraform inputs and independent ARM verification; extend `test_agent_control.py`/runtime tests for configured origins, drift rejection and the unchanged empty-origin/native-client case. Verify focused Python/type/Terraform checks and document origin configuration/readback, without weakening audience or artifact checks.

## 3. Complete minimal browser journey

- [x] 3.1 Implement validated runtime configuration and MSAL initialization, stable SPA redirect, user-approved tab-scoped sessionStorage agent token acquisition and sign-out; verify component/auth and real-SDK browser tests for invalid config, expired/denied access, wrong endpoint, redirect handling, no token export and no automatic question resend. Start the UI runbook's authentication/configuration section.
- [x] 3.2 Implement the typed official-SDK research adapter with one data part, strict version/output modes, progress mapping, successful terminal validation, safe failure categories and stop handling; verify contract/unit tests for UTF-8 8192-byte inputs, 16 KiB output and 1 MiB stream bounds, 120-second deadline, single in-flight request, truncated streams and no generation replay. Keep GetTask parity in acceptance checks, not every successful UI request.
- [x] 3.3 Implement the responsive labelled chat page, early-access banner, inert answer/limitation rendering, numbered HTTPS-only citations, keyboard stop/navigation and simple daisyUI light/dark theme; verify Testing Library/Vitest and accessibility tests including hostile strings, unsafe URLs, no-match/refusal, overload/error, unknown text and unconfirmed cancellation. Document independent questions and safe citation behavior; do not add empty feed/item pages.

## 4. Owning secretless UI infrastructure and checks

- [x] 4.1 Add `infra/ui-identity` and scoped preparation/readback for a distinct single-tenant SPA client with only `news.agent`, derived stable UI redirect and exact adoption/consent inputs; verify mocked-provider Terraform and platform tests reject secrets, unexpected grants, origin/ID mismatch and unrelated registration changes. Document preparation and required operator consent without broad grant fallback.
- [x] 4.2 Add `infra/ui`, nonroot immutable static image/build, registry-pull-only identity and runtime config/security-header generation in the retained ACA environment; register owning azd hooks/layers and exact readback. Verify Terraform/platform tests plus a local container smoke test for image/config/origin, no-store HTML/config, immutable assets, CSP, disabled content/query logging and the reviewed scale profile; document deployment and rollback.
- [x] 4.3 Integrate workspace lint/typecheck/unit/component/build and local authored-browser integration into the existing primary/CI gates, with no automatic Azure deployment; verify hostile-canary tests and Playwright diagnostics cannot retain live content/tokens. Document README installation and focused commands; Azure tests must use transient interactive authentication, not saved storage-state.

## 5. Integrated delivery and measured publication

- [x] 5.0 Implement the separately approved versioned manifest-pin compatibility fix; verify original pin/digest preservation, the exact UI-workspace set, unknown-input rejection and old-provenance rejection against current source, with no schema/budget/journal change or evaluation execution.
- [x] 5.1 Run `bash scripts/check.sh` and local browser journey tests before deployment; record exact source/configuration hashes and command outcomes, distinguishing authored tests from live evidence and preserving the unrelated dirty worktree and evaluation receipts.
- [x] 5.2 Review scoped identity/app readiness, the UI cost/replica estimate and owning UI-identity/UI/agent plans in the retained azd environment; verify no existing MCP/model/schedule/data/evaluation change, no environment replacement and no unrelated grant. Obtain required owning-plan authorization before apply.
- [x] 5.3 Apply/deploy only the approved owning layers and immutable UI/CORS-agent images; verify independent exact image/configuration/SPA-permission/UI-origin/agent-origin readback and HTTPS headers. Preserve prior revisions and state for rollback; deployment/health alone do not complete browser acceptance.
- [ ] 5.4 With the user ready at the stable UI URL, run the real signed-in browser research/progress/completed-task/citation journey and deployed keyboard/axe checks; verify same-user delegated access and explicit live authorization failure without content capture. Separately label routed hostile/no-match/cancellation fixtures as UI-only checks, not real research-quality evidence; record safe outcomes and observed usage estimates without resetting existing costs.
- [x] 5.5 Selectively commit/push only this slice after local/Azure checks and verify passing CI for the exact implementation commit; exclude baseline implementation and unrelated prompt/skill edits, and retain the source/image/evidence association.
- [x] 5.6 Publish the measured UI status/runbook/README and separate exact-source status CI; verify this slice's checked tasks match actual evidence, the UI remains early access, PRD-2 evaluations stay open, and later feed/search/structured-citation/full-phase gates are not claimed complete.

## Workflow follow-up

Publication sequencing exception (2026-11-01): after the concrete tooling
limitation was reported, the user approved committing the deployed implementation
and measured status with exact-source CI while unavailable automated Azure checks
remain open. The tools control VS Code's integrated browser, not the user's
existing regular-browser session. Task 5.4 remains unchecked; manual confirmation
does not establish automated parity, authorization-failure or deployed axe proof.
No new sign-in, credential export, evaluation replay or archival is authorized.

Implementation publication: commit `9153485d1cdffb1f7d982c239786a90369f8e316`
passed exact-source CI run `41329362328`. Its isolated selective tree passed the
primary gate: 301 evaluator tests, 1,577 application tests with 67 conditional
skips, 31 frontend tests and four authored browser/axe checks. Types, runtime
checks, frontend build and Terraform checks passed. Fewer tests than the broader
dirty-worktree run reflect deliberately excluded parked evaluation implementation,
not omitted publication-tree tests. The publication source hash matches the
retained lofi deployment. All 52 parked paths were hash-checked unchanged.

Measured-status publication: commit `14e5956b36869d764040abe8298a4b31a8c5c2c4`
passed separate exact-source CI run `41330011319`. Automated signed-in Azure
acceptance is still open; this publication does not complete task 5.4 or PRD-2.

Local implementation evidence (2026-10-31): locked npm installation, frontend
lint/typecheck/build and 21 unit/component/official-SDK tests passed. The authored
browser journey and axe checks passed in the pinned Node 24/Playwright Podman
runner after correcting heading order. Host Chromium was missing `libnspr4.so`;
sudo installation was unavailable, so no host permissions were changed.
The current production image's nonroot/configuration/cache/security-header/
callback/log-canary smoke check passed. Focused Python checks passed, including
165 origin/serving/control/runtime tests and subsequent UI helper cases.
Terraform: 17 agent, four UI identity and four UI app mocked-provider tests passed.
README/runbook/phase links and shell syntax passed. Primary Python/frontend/
browser/spec stages passed: 503 evaluator tests; 1585 application tests with 67
conditional skips; 21 frontend tests; authored browser/axe. After formatting only
the two new Terraform test files, all primary Terraform validation/test stages
were resumed and passed; all six Python package builds passed.
Application source SHA256: `7a62f63a3e66e658dda6d052fc1ad682e8ac7424744e34907c3777d0b65cfd83`.
Scoped read-only SPA readiness passed and found no existing SPA; retained azd
configuration was backed up privately. Azure,
implementation/status CI and publication tasks remain unchecked below their
own gates; these local checks are not real-user or research-quality evidence.

Cloud preparation follow-up: the approved identity plan created the SPA and
service principal but consent creation failed with `Authorization_RequestDenied`.
The user granted admin consent; exact `news.agent` readback passed and its
Terraform adoption imported only that grant with zero cloud mutations.
The first UI image build failed because ACR's classic builder does not support
`COPY --chmod`. A compatible build-time chmod step retained nonroot runtime;
local production-container checks passed and both owning ACR images built.
Final image-input source SHA256:
`fd66513de4a4c136fdf3f08f4636c610f8750996502e33494f7a52884f7f5bfd`.
User-approved UI plan: `ee52458dc2b22a74ddca39854516307ba3d5a1654baa6d79b502727ef2cc85b1`
(three additions: app, own registry-pull identity and AcrPull grant).
User-approved agent plan:
`0f6eaf6450fa1980de6e93cca44b9c552ce2926d9c75754a109d65d313fe1392`
(image, runtime revision and exact UI origin only; no destroys).
Official France Central active meters imply USD 0.027/hour compute for the
reviewed 0.25 CPU/0.5 GiB profile, plus USD 0.4/million requests before free
allowances; this excludes builds, networking, other resources and inference.
These plan/build receipts are not deployed browser acceptance.

First owning UI/agent applies succeeded; independent agent image/configuration
readback passed. UI HTTPS/config/CORS probes passed, but UI readback initially
rejected Azure's omitted `minReplicas` for the configured zero-minimum profile.
The narrow verifier accepts omitted/zero only and rejects one; focused tests and
live readback passed. The initial user browser check then failed sign-in:
MSAL 5 disallows redirect login with memoryStorage. The user explicitly approved
MSAL-managed tab sessionStorage (no chat persistence or exported credentials).
This replaces the mistaken memory-cache assumption, not the delegated identity
or callback. A real SDK browser regression now verifies PKCE redirect preparation
without network sign-in; both authored browser/axe and MSAL cases passed.
The corrected UI rollout remains pending and signed-in research acceptance
is still unchecked. No baseline or paid research invocation was started.

Resume readback (2026-11-01) established that the initial UI was still active and
the interrupted auth-fix apply had not updated it. A fresh same-scope preview
retained the previously approved correction, with one UI image/revision update
and no creates/destroys; native apply succeeded. Independent UI/SPA/consent and
unchanged-agent image/config readback passed, as did live HTML/config/security
headers, POST preflight and visible unauthorized response.
UI input source: `05cec1d5010b79aba1b913b6a08560e3783bd082f47846445dffc851f169a8db`.
The user attested "Sign-in and cited answer work", then requested a default
latest-news feed with optional research. This confirms the manual journey only;
task 5.4's complete automated evidence and publication gates remain open.
The separately planned `ui-news-feed` slice does not silently expand this change.

- Review and archive only this change after its local, Azure and publication
  obligations are verified and archival is requested.
- Propose the subsequent feed/search/item-context slice with a typed NewsCatalog,
  direct-MCP CORS/consent/protocol checks and an honest timestamp-tie/paging decision.
- Resume versioned evaluations separately with prior costs/receipts preserved;
  this UI delivery does not restart a halted baseline.
