# Tasks

Implemented locally; cloud acceptance is not yet claimed.
The first UI's successful user sign-in/answer attestation does not complete its
remaining automated evidence or implementation/status publication gates.

## 1. Prerequisite and exact modern client

- [ ] 1.1 Before accepting and publishing this slice, complete and record `ui-spike-and-shell`'s remaining image/input binding, deployed browser evidence and selective implementation/status CI gates; verify its ledger without marking PRD-2 evaluations or unrelated work complete. User-approved sequencing permits local implementation and the exact reviewed early-access rollout for regular-browser verification while these acceptance/publication prerequisites stay open; user sign-in occurs only in their regular browser.
- [x] 1.2 Add the exact MCP browser dependency and typed recent/search NewsCatalog; within the 30-minute compatibility bound verify pinned 2026-07-28 server/discover, required headers/body metadata, recent-news/search structured results and cancellation against the current authored Python SDK server. Verify locked installation, TypeScript and contract tests; record protocol decisions in the owning ADR/runbook.

## 2. Browser MCP access and identity

- [x] 2.1 Implement reusable exact-origin CORS mechanics with explicit service policies and the MCP POST/header policy; verify allowed/denied/duplicate origins, unsupported method/header rejection, zero preflight auth/admission/data/model work, real success/error headers and unchanged agent/native-client behavior in focused Python tests. Document browser-origin behavior in the MCP runbook.
- [x] 2.2 Wire strict MCP origin normalization through runtime, native azd encoded inputs and independent ARM image/config/identity/origin readback; verify drift/invalid-input rejection and unchanged profile/workload authority through platform and mocked-provider Terraform tests. Document owning preparation/readback commands.
- [x] 2.3 Extend the existing SPA registration/consent with only MCP news.read while preserving news.agent and redirects; extend trusted UI config/CSP and per-resource MSAL token acquisition. Verify exact-inventory/adoption tests, two-audience auth tests and Terraform permission deltas; document admin-consent failure/recovery without broader roles or secrets.

## 3. News-first interaction

- [x] 3.1 Implement bounded recent-news reads and the latest-20 landing page with inert title/summary/source/category/time/links, refresh and distinct loading/empty/error states; verify order/ties, no hidden date cutoff, malformed responses, 90-second/1-MiB bounds, single in-flight load, cancellation and sign-out cleanup in unit/component/contract tests. Document the bounded-view/no-pagination behavior.
- [x] 3.2 Add the top native search form using MCP search_news only on submit, relevance-ranked latest-20 results and clear-to-latest behavior; verify zero requests while typing, the 2048-character query boundary, stale-load cancellation and distinct empty/error states. Document intentional search-embedding cost and the unchanged A2A research path.
- [x] 3.3 Move research to an accessible right-hand panel with open/close controls, collapsed by default, explicit general/item actions and removable current-news context; verify full-width news when closed, preserved transient state without replay, focus return, responsive layout, exact submitted item IDs and stale idle-context cleanup, with frozen in-flight context and existing stop/sign-out behavior.
- [x] 3.4 Add authored browser/axe and hostile-content checks proving feed load/refresh/panel opening dispatch zero agent or embedding requests, submitted search calls only MCP, and explicit selected-item research calls A2A and yields safe citations; integrate them into existing checks and document local versus live evidence without content-bearing diagnostics.

## 4. Owning delivery and publication

- [x] 4.1 Run the primary local gate before deployment; record exact source, npm manifest/lock and configuration bindings, package/build outcomes and first-UI prerequisites. Preserve unrelated worktree changes and all evaluation receipts/costs.
- [x] 4.2 Review the exact existing SPA/MCP/UI native azd plans: only intended MCP delegated consent and app/image/origin/config changes, no new models/resources or agent/OBO changes. Obtain required owning authorization; if admin consent is denied, preserve partial state and adopt only the user's exact grant.
- [x] 4.3 Deploy only approved owning layers/images in the retained environment; verify independent identity/image/config/CORS/security-header readback and preservation of existing schedules, stored data, agent grants and profile. Record failures honestly; never recreate infrastructure or replay an uncertain mutation blindly.
- [ ] 4.4 Verify the real signed-in Azure default feed, zero automatic inference, submitted MCP search, open/close right-panel behavior, explicit current-news A2A research and citation navigation, keyboard/axe and authorization failures with safe metadata-only evidence; keep user attestation separate from automated evidence and retain search-embedding/research-chat estimates without resetting previous costs.
- [ ] 4.5 Selectively commit/push only this slice after local/Azure gates, verify exact-source implementation CI, then publish measured docs/status with separate CI. Verify unchecked filter/paging/evaluation/full-phase tasks remain open and no unrelated baseline/prompt/skill changes were staged.

## Workflow follow-up

Publication sequencing exception (2026-11-01): the user approved selective
publication and subsequent filters with unavailable automated Azure checks still
open. The integrated-browser tooling cannot control their existing regular-browser
session. Task 4.4 and the first-UI browser acceptance remain unchecked; regular-
browser confirmation is manual evidence, not automated parity or axe proof.
UI search/research usage is not fully metered; hosting/build costs are also
unmeasured. Existing evaluation estimates and reservations remain separate and
unchanged. No new authentication session, exported credentials or evaluation
attempt was made for publication.

Retained deployment evidence binds the lofi UI source to
`ecb8de9d2021caa8b80818073b09216fb1c59aa38bc049f9b852a68cfe1a9cdd`,
with HTTP 200, lofi stylesheet verification and preserved configuration. The
prior feed/MCP source and agent source remain in their original private receipts.
Publication must not retroactively replace those build-time source hashes with
a Git commit identifier or imply all previously dirty build inputs were published.

Local evidence (2026-11-01): frontend lint/typecheck/build passed, with real
JavaScript MCP 2.4.0/Python MCP 2.3.0 modern discovery/read/search/cancellation
contract tests. Component tests cover latest-first defaults, no calls while
typing/opening the panel, submitted search, exact selected IDs, close/reopen
without replay, stale-context cleanup and post-sign-out result rejection.
Three headless authored browser cases passed, including desktop/mobile layout,
keyboard citation navigation, hostile inert rendering and axe. The real-SDK
MSAL regression uses authored metadata and performs no user sign-in.
The current nonroot production-container configuration/cache/header/callback/
log-canary smoke check passed. Owning Terraform tests passed (five UI identity,
five UI app and six MCP), as did focused typed Python checks and 50
origin/configuration/permission/readback cases. The final primary gate passed:
503 evaluator cases, 1606 application cases with 67 conditional skips, 30
frontend cases, three authored browser/axe cases and all Terraform stages.
All six Python packages built. A subsequent focused 22-case typed test run
verified the UI-specific two-resource consent inventory, including rejection of
foreign/duplicate/broader grants; the agent's single-resource consent helper was
not weakened. No feed permission or cloud application was changed.

The separate first-UI headed check timed out before sign-in and dispatched no
research. The user declined future test-browser sign-ins and explicitly approved
local feed implementation with release prerequisites still open. Only their
regular browser is used for future live sign-in. The first UI's release evidence
and publication are not marked complete, and no feed deployment or new cloud
permission is claimed.

Cloud preparation: the user approved the exact SPA update/MCP consent plan.
The SPA request changed successfully; consent creation was denied by Entra.
The user granted `news.read` admin consent in their regular browser; exact
two-resource consent readback passed, followed by a Terraform import-only
adoption with zero resource mutations. Existing `news.agent` and redirects
were preserved. Both immutable app images built with source
`d345926e97eddba8515004528791df7a8f6d4dd1ff79c892675c139dd37535df`.
Reviewed MCP plan `eb0676b73d0dee504e6888dcb51edfdcbe7ef4c17f9cbd74dbbb04eeb4e842c2`
changes only its existing image and UI origin; reviewed UI plan
`99dfca2ba0dcb32164285ebb9593856e9cb6e271539c552993628e9b5757302c`
changes only its image/revision and trusted MCP config. Each has one update,
zero additions/destroys. The user explicitly approved both exact plans and
early-access rollout while remaining automated acceptance/publication stays
open. Deployment/readback and regular-browser acceptance are not yet claimed.

Early-access deployment follow-up: native MCP and UI applies succeeded, each
with only its reviewed existing-app update. Independent MCP/UI image,
configuration, identity, delegated-consent and profile readback passed.
The unchanged agent image/configuration readback passed separately. Live MCP
POST preflight returned 204 and anonymous access returned 401; UI HTML,
six-field configuration, CSP and hashed assets were verified over HTTPS.
No migrations, model changes, data-write path or schedule/grant widening was
introduced. Regular-browser feed/search/context verification, remaining
automated acceptance and both publication obligations stay open.

The user confirmed latest news, submitted search and contextual A2A work in
their regular browser. They reported page-wide scrolling for long agent replies;
the UI-only correction makes the panel viewport-bounded, independently scrollable
and keyboard-focusable. Frontend type/lint/30 tests and four headless browser
cases passed, including wheel/PageDown scrolling with unchanged page scroll.
The user approved plan
`afb3ea327e331f43289573fa4a0bed2775f2ef0ddc8e11bff8b9178fdd44f97e`
(one UI image/revision update, no additions/destroys or other app/config changes).
Native apply and independent UI image/config/CSS readback passed, with source
`83f2586bc144949e7cb7e5bda00748aa720b75a29691e375d5ce579fa65c85d6`.
The user then confirmed independent scrolling works. Their earlier mistyped
search issue was no longer reproducible; inspection found no lexical/similarity
cutoff in the MCP ranking path, and no correction heuristic or search change
was introduced. These manual observations do not close missing automated
Azure evidence or CI/publication tasks.

The user requested DaisyUI `lofi` as the default and explicitly requested its
deployment. Custom light/dark palette overrides were removed; the explicit dark
toggle remains and returns to lofi. Frontend lint/typecheck/build and 31 tests
passed. The reviewed native UI plan admitted only an image/revision update
(no configuration, MCP, agent, permission or resource change); apply and
independent image/config/live CSS readback passed with source
`ecb8de9d2021caa8b80818073b09216fb1c59aa38bc049f9b852a68cfe1a9cdd`.
Remaining formal acceptance/publication stays unchecked.

- Review and archive only after all actual acceptance/publication gates pass and
  archival is requested.
- Propose filter/detail/multi-selection or a real cursor separately;
  do not add timestamp-only pagination while claiming complete results.
