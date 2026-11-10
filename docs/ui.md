# Browser UI runbook

The [daily briefing](briefing.md) panel extension is deployed early access.
It displays a shared TL;DR above a collapsed full summary when an artifact is
available, without generation on reads/expansion or changes to research context.
The first full artifact is now published after an explicitly authorized,
audited same-day retry: a 1,026-word summary with an 82-word TL;DR. Earlier
rejected/incomplete attempts were retained, not hidden or reset. Actual
scheduled execution and signed-in qualitative acceptance remain open.

The [HTTP catalogue migration](../openspec/changes/archive/2026-11-04-ui-http-news-catalog/tasks.md)
is deployed early access with stored-item pages and capped browse continuation.
Local checks and owning image/config/asset/identity/backend preservation passed;
new authenticated regular-browser/cache/deployed accessibility acceptance remains
open. Use [HTTP catalogue migration](#http-catalogue-migration) for current behavior
and commands. The initial-UI/MCP sections below retain historical deployment/
rollback context; their old user confirmations are not new HTTP acceptance.

Status: deployed early access. The user confirmed latest news, submitted search,
contextual agent interaction and independent panel scrolling in their regular
browser. Full automated Azure acceptance remains open; this is not full phase acceptance.
Implementation commit `9153485d1cdffb1f7d982c239786a90369f8e316` passed exact-source
CI run `41329362328`; measured-status commit
`14e5956b36869d764040abe8298a4b31a8c5c2c4` passed separate CI `41330011319`.
On 2026-11-01 the user approved selective publication and filter implementation
with those unavailable checks explicitly open. Automation can control the
integrated VS Code browser, not their existing regular-browser session; another
test-browser sign-in or exported authentication state is not permitted.
The [owning change](../openspec/changes/archive/2026-11-04-ui-spike-and-shell/tasks.md) records actual
checks. [PRD-3](prd-3.md) owns sequencing; [capabilities](prd-3-capabilities.md)
and the [stack ADR](adrs.md#ui-stack-comparison) own behavior and decisions.
PRD-2 evaluations remain open.

## Compact news toolbar

The [compact-toolbar slice](../openspec/changes/archive/2026-11-04-ui-compact-news-toolbar/tasks.md)
removes the visible main news eyebrow/title/intro and puts Refresh alongside
Apply/Reset in the filter toolbar. Search keeps a concise submitted-query/
relevance/bounded-result line; Clear search occupies the same action position.
The semantic news heading remains visually hidden for accessible navigation and
Back-to-news focus. Detail-page titles are unchanged. Controls wrap on mobile.
Refresh/Clear search do not submit draft filters; existing applied-snapshot,
HTTP cache, paging and A2A behavior is unchanged.

This refinement is deployed early access. Implementation `1c44c0a` passed
exact-source CI `41493885878`. Its original immutable UI source was
`1842f4750ffc15f43bc802017e6167d1f6b23148d3d17dea339787418052b684`.
On 2026-11-02 the user approved the fresh image/runtime-revision-only plan and
publication with signed-in Azure toolbar/accessibility acceptance open.
Native azd applied one existing UI update with no creates/deletes; owning
image/configuration/identity/consent/API readback passed. The served scripts/CSS
matched the pinned production build byte-for-byte. UI health, detail SPA
fallback, CSP/cache headers and six unchanged backend/job fingerprints passed.
Anonymous Azure checks at 1440px and 390px confirmed the removed hero gap,
no overflow and zero axe violations, without sign-in or protected requests.
These checks do not prove signed-in Refresh/Clear search behavior or toolbar
alignment in Azure; that acceptance remains explicit in the checklist.

## Browser-local timestamps

The [timestamp slice](../openspec/changes/archive/2026-11-04-ui-browser-local-timestamps/tasks.md)
is deployed early access. Implementation `a6d65f2` passed exact-source CI
`41502389782`. Its immutable UI source is
`3743b4c6bf715650e2517de2ebfc51b8eb3f4222b9d0f5bae431ea9348f251c8`.
Cards, detail and latest-page-read metadata use the browser's locale/timezone
with an explicit instant-specific UTC offset, including daylight-saving and
fractional-hour offsets. Raw timestamp values and server result order stay intact.

Article dates later than the device clock show "Future-dated". This describes
the stored instant, not a scheduled publication or a confirmed publisher error;
dates are not clamped, hidden or corrected. The shared display clock refreshes
once per minute and on focus/visibility resumption, without refreshing data,
reapplying filters, changing server-reported cache age or invoking the agent.
An inaccurate device clock can affect the indication. Existing local-calendar
filter semantics are unchanged.

On 2026-11-02 the user approved the fresh image/runtime-revision-only rollout
and publication with signed-in timestamp/accessibility acceptance open.
Native azd applied one existing UI update with no creates/deletes; owning
ready-image/configuration/identity/consent/API readback passed. All three served
script/CSS assets matched the pinned production build's filenames and bytes.
UI/API health, detail SPA fallback and six unchanged backend/job fingerprints
passed. Anonymous Azure shell checks at 1440px and 390px found no overflow,
script errors or axe violations and made no protected requests.
The 13 authored browser journeys verify the timestamp behavior locally;
these anonymous Azure checks are not signed-in timestamp proof. That acceptance
remains open in the checklist, and earlier phase/API acceptance is unchanged.

## Daily shared briefing

The [daily briefing change](../openspec/changes/archive/2026-11-07-daily-news-briefing/specs/daily-news-briefing/spec.md)
owns the contract. The Agent panel reads `GET /api/v1/briefing` using the news
audience and delegated `news.read`, only when signed in and open. Its independent
HTTP lane never calls A2A, generates content or changes research snapshots.
The matching API/schema and default-off backend feature are now deployed/enabled.
An unavailable endpoint remains a visible, retryable briefing-read error, not an
empty-news result, and the composer remains usable. Deployment/usage and the
open successful-generation boundary are recorded in the [briefing runbook](briefing.md).

The TL;DR is below heading/Close and above the research notice/context/composer.
Generation time is the only healthy metadata line before the TL;DR; the scope,
refresh-ready, cutoff/window/count and last-read/cache diagnostics are not shown.
Native details contains the complete cited summary; it starts collapsed and
resets only for a different published version. Closing/reopening or rereading
the same version retains expansion. Publisher text is inert; original citations
permit HTTPS without credentials only. Dates retain their wire strings and
display in the browser's locale/timezone with explicit offsets.

The panel distinguishes no publication, no news, no material changes, limited
evidence, stale content and refresh/read failures through concise notices. The
last successfully read publication remains visible after a later read failure,
with an explicit freshness warning. Operational window/cutoff/read/cache values
remain in the protected DTO, not an expanded diagnostics block.

The [architect-focused refinement](../openspec/changes/archive/2026-11-07-architect-focused-briefing/specs/architect-focused-briefing/spec.md)
adds optional `editorial_policy: "architect-v1"`. Its TL;DR plus narrative have
no minimum and a combined maximum of 1,000 whitespace-delimited words, excluding
headings and citations. Omitted/null policy retains the historical full
900–1,100 narrative-word validator, including the published 1,026-word narrative
and 82-word TL;DR; unknown policies fail validation. The collapsed summary's
estimated reading time rounds total TL;DR/narrative words up at 200 words/minute,
so the legacy publication estimates six minutes, not a fixed five.

`coverage: "no_material_changes"` requires architect policy, positive reviewed
evidence and null TL;DR/empty sections/citations. It shows only the concise notice
that no material changes were identified in reviewed stored reporting, not a
claim about all real-world AI changes or fabricated content. Zero stored news,
missing publication and transport failures remain separate outcomes.

The main applied-filter badge row and its reserved spacing are removed for
default and selected filters. Draft edits still dispatch nothing; Apply/Search/
Reset retain their explicit semantics. Research filter chips and submitted
question/answer context snapshots remain visible and immutable.

Local authored policy/compatibility, metadata order, absent badge spacing,
desktop/mobile geometry, keyboard/citation and axe regressions pass. These are
fixture checks only; this refinement has not been deployed or accepted in a
signed-in Azure browser, and prior scheduled/quality acceptance stays open.

Reads are throttled to at most one start per minute, including retries, focus,
visibility resumption and close/reopen. Open visible panels periodically reread;
hidden documents resume when visible. A Retry within the minute schedules the
next permitted read, rather than bypassing the limit. Close, sign-out and teardown
abort owned reads and ignore late completions without stopping research.
Nothing is persisted in browser storage.

Authored component/HTTP-transport and desktop/mobile Chromium/axe journeys cover
strict envelopes, complete expansion, keyboard citations, safe text, versions,
status/error recovery, local dates and independent scroll/context preservation.
These are local fixtures, not signed-in Azure, generation-quality or scheduled-job
acceptance. All real Azure acceptance remains in the owning change.

## Local development

The browser lives in the root npm workspace, separately from Python's uv workspace.

```bash
npm ci --no-audit --no-fund
npm run -w services/web dev
npm run -w services/web lint
npm run -w services/web typecheck
npm run -w services/web test
npm run -w services/web build
npm run -w services/web e2e:local
```

Local authored transports are not Azure authentication or research evidence.
If local Chromium system libraries are unavailable, use the pinned isolated
browser runner with an existing Docker or Podman runtime instead of changing
host permissions:

```bash
NEWSLOOM_BROWSER_ENGINE=podman bash scripts/check-ui-browser.sh
NEWSLOOM_BROWSER_ENGINE=podman bash scripts/check.sh
```

The runner uses the same source and Node 24, builds only an authored-test target,
and removes its own container/image. The production Docker target remains the
nonroot static server; it does not include the browser harness.
The real browser journey uses deployment-provided configuration and a stable
HTTPS SPA redirect, not the existing native loopback callbacks.

## Authentication and configuration

The UI loads public `/config.json` without caching and validates it before
initializing MSAL. Deployment supplies the tenant, separate SPA client, existing
agent URL and `news.agent` scope. Keep actual deployment values in ignored azd
configuration, not source, committed JSON or test snapshots.

The first UI acquires only an agent-audience delegated token. The existing agent
performs secretless OBO to MCP; no browser MCP grant is needed yet.
Sign-in redirects do not save or automatically resend questions.
MSAL 5 redirect login requires its tab-scoped sessionStorage cache; memoryStorage
is not compatible with redirects. The user approved this compatibility correction.
Tokens are never cached in localStorage or exported; sign-out clears the MSAL
session and in-memory thread.
Questions are independent; the UI does not create agent memory or persistent
chat history. Tokens stay within the authentication session and authorization
channel; never export browser storage-state as test evidence.

## Agent browser origin

The agent's existing `AGENT_ALLOWED_ORIGINS` configuration is a comma-separated
list of canonical exact HTTPS origins, with no trailing slash, credentials,
wildcards or default-port suffix. Empty means no browser origins.
The owning preparation hook produces `AGENT_ALLOWED_ORIGINS_BASE64` for native
azd's Terraform JSON input. Do not hand-edit that encoded value.

Preflight permits the existing discovery GET and A2A POST paths with Authorization,
Content-Type, A2A-Version and Accept headers only. It does not consume request
admission, authentication or inference. Responses include exact-origin headers
on success/errors/stream startup; cookies and credentialed CORS are not enabled.
Preflight cache lifetime is 300 seconds.

Independent agent readback compares the normalized configured origin list,
immutable image and existing identity/permissions. Origin drift is a failure,
not a health-check success. Native clients without Origin retain their contract.

## Answer and citation behavior

The UI shows received progress followed by the completed validated text answer,
not unvalidated draft tokens. It preserves no-match, refusals, unknown text and
limitations, including the stored-summary evidence boundary.
Citation labels use supplied numbers and hostnames, not invented article titles
or quality badges. Text is inert; only credential-free HTTPS URLs are clickable.
Stopping a stream does not claim confirmed server cancellation without a receipt.

## Deployment and acceptance

Owning layers are `ui-identity` and `ui`; only the existing agent layer changes
to add the UI origin. UI registration requests only delegated `news.agent`.
`UI_ENABLED` and `UI_CONSENT_ENABLED` default to false. Preparation uses exact
existing agent IDs, detects UI name collisions and requires explicit
`UI_CLIENT_ID` for adoption. It never creates registrations or consent directly.

The stable UI origin is derived from the retained ACA environment domain and
app name before registration; both app and identity readback must agree.
The SPA registers `/auth/callback` for MSAL 5's redirect bridge and `/` for the
logout return. No loopback, preview or wildcard redirect is registered.

After local checks, review the identity plan first. Once its actual client ID
is available, review the app and CORS-agent plans against that output. This
staging avoids placeholder client IDs and does not waive either owning review.

```bash
uv run --locked newsloom-platform prepare-ui-identity
azd provision ui-identity --preview
# Apply only after the owning preview is approved.
azd provision ui-identity
uv run --locked newsloom-platform build-ui
uv run --locked newsloom-platform prepare-ui-layer
azd provision ui --preview
# Set AGENT_ALLOWED_ORIGINS to the reviewed UI_ORIGIN in ignored azd state.
uv run --locked newsloom-platform build-agent
azd provision agent --preview
# Apply only the approved app and agent plans.
azd provision agent
azd provision ui
uv run --locked newsloom-platform verify-agent
uv run --locked newsloom-platform verify-ui
```

The app uses the retained ACR, immutable images and its separate registry-pull
identity. It starts at Consumption 0.25 CPU/0.5 GiB, min zero/max one replicas.
Cold starts and hosting costs must be measured separately from chat estimates.
The web app keeps one replica running (`min_replicas = 1`, like the agent and API).
Scaling from zero took about 40 s on 2026-11-05: about 14 s of platform sandbox setup
and about 25 s before the new replica received traffic; nginx itself starts in about
1 s. Keeping it warm costs about USD 6 per month at France Central idle rates.
Do not provision a new environment or use a deployment token as fallback.

For a local static-server smoke test, use the existing container runtime:

```bash
podman build -f services/web/Dockerfile -t localhost/newsloom-ui-local .
uv run --locked python scripts/check_ui_container.py --engine podman --image localhost/newsloom-ui-local
```

Docker is also supported by the smoke checker when available. Only the checker's
own randomly bound container is stopped. Public authored configuration is used;
this test does not access Azure.

The primary check runs local authored browser tests. Azure browser verification
is separate and interactive:

```bash
npm run -w services/web e2e:azure
```

Set `NEWSLOOM_UI_ORIGIN` and an authored `NEWSLOOM_UI_QUESTION` only in the local
process environment. A headed browser/desktop is required for user sign-in;
never commit browser authentication state. The reporter records safe test
counts/status only, not question values, raw errors, traces or screenshots.
Record local, Azure and exact-source CI evidence separately.
Browser traces, HARs, screenshots, console content dumps and persisted sign-in
state must not retain live questions, news, answers or credentials.

## Rollback

Preserve the prior immutable images, source hashes and ignored azd state.
Reapply the reviewed previous UI/agent image configuration through the owning
layers. If withdrawing browser access, remove only the UI origin from agent
configuration and verify readback; preflight caches may last 300 seconds.
App-only withdrawal must not reprovision the identity layer disabled: registrations
and workload identities resist destruction. Never delete unrelated grants or
reset the evaluation ledger during UI rollback.

## Latest news, search and optional research

The [feed slice](../openspec/changes/archive/2026-11-04-ui-news-feed/tasks.md) is deployed for
early-access verification, with unavailable automated acceptance still open and
selective implementation/status publication verified.
The default signed-in page shows the latest
20 stored news items without a date cutoff. Refresh uses recent-news access only.
The top search box calls MCP `search_news` only on submit; clearing it returns
to recent news. Search uses the existing bounded query-embedding path, not A2A.
Typing, browsing and opening the agent panel do not invoke inference.

The right agent panel opens/closes explicitly and expands below news on narrow
screens. Its viewport-bounded region scrolls independently with the mouse wheel
or keyboard. Selecting a story sets visible removable item context; Send dispatches
the existing A2A research request. The context is frozen during a request, and
stale idle selection is cleared when the displayed news changes. Closing retains
transient interaction state without replay. Nothing is saved across sign-out.

The deployed UI defaults to DaisyUI's built-in `lofi`, without custom palette
overrides. The existing theme control optionally switches to built-in `dark`
and returns to `lofi`; system dark preference does not override the default.

Runtime configuration adds `mcpUrl` and the existing MCP `news.read` scope.
MSAL acquires separate audience-bound tokens for news and agent access.
`UI_MCP_PERMISSION_ENABLED` owns the SPA's additive MCP permission/consent;
`UI_NEWS_ENABLED` owns the feed UI/configuration. Keep the permission enabled
during an app-only rollback so existing consent is not accidentally removed.
Both flags must be explicitly reviewed before enabling the feed. No new role,
resource or model is needed.

MCP browser access pins protocol 2026-07-28: `server/discover`, not legacy
initialize; required headers include MCP-Protocol-Version, Mcp-Method and Mcp-Name.
The local contract test runs the real installed Python MCP SDK on loopback with
authored data only. It is not production-user or model evidence.

User sign-in happens only in the user's regular browser. No separate test-browser
sign-in, credential export or saved storage-state is used. Automated live checks
that cannot run through that workflow remain explicitly unchecked.

## Source, category and date filters

The [filters slice](../openspec/changes/archive/2026-11-04-ui-news-filters/tasks.md) is deployed as
early access. Local/SDK/authored browser checks and owning Azure image/configuration/
permission readback passed; regular-browser filter confirmation and unavailable
automated signed-in Azure acceptance remain open. Its final source is
`87e78e9ceb6e695e6f5c3fb305df39ad12c192afbb4ad16f24767bab258ac9da`.
Filter implementation `9604f3be4eaa4efdd45a0588b1296ca1007dfc53` passed
exact-source CI `41342706269`; measured-status publication `0869a45` passed separate
CI `41343382008`. This does not complete the signed-in acceptance gate or authorize archive.
It reuses existing MCP `news.read`, A2A `news.agent` and runtime configuration.
NewsCatalog exposes source/category discovery and optional-query filtered search
without leaking SDK types to components, preserving the later HTTP adapter seam.

Source IDs and category labels come from authorized `list_sources`, once per
signed-in view. Discovery and news reads have separate bounded cancellation lanes,
at most one request per lane; catalogue failure does not block date-only browsing.
Unavailable choices are disabled with explicit retry, not invented or silently
substituted. Existing applied constraints remain visible.

Editing controls dispatches nothing. Apply uses the last submitted query; Search
submits draft query and filters together. Reset clears metadata but preserves that
query; Clear search retains applied filters. Any time omits date bounds. Other
presets and inclusive custom dates use the reader's local calendar and serialize
UTC-aware inclusive `from` and exclusive `to`; DST is not treated as fixed 24-hour
arithmetic. Invalid dates fail visibly before dispatch.

Only explicit semantic queries request embeddings. Query-less metadata search
does not invoke inference; filtering never sends A2A automatically. Each explicit
research request sends structured filters and optional selected ID. Its displayed
context remains attached to the answer, even after browsing filters or selected
news change. Questions remain independent and sign-out clears transient state.

The confirmed follow-up order is cached API with detail/cursor contracts, UI HTTP
adapter, then versioned evaluations; see [PRD-3](prd-3.md#delivery-plan) and the
[API direction ADR](adrs.md#explicit-filters-and-subsequent-api-transport).
No API, cache, detail/pagination route, grant or new model is implemented here.

Build contexts must exclude generated/cache/environment directories and their
contents explicitly. Azure CLI's file-wise ACR uploader can re-include children
after a directory-only rule when an earlier source allow rule matches them.
Keep recursive rules such as `**/dist/**`, `**/node_modules/**` and
`**/test-results/**`; the owning regression guard covers the complete list.
Verify the actual archive when changing context rules, rather than assuming a
local Docker/Podman build exercises the Azure uploader.
The corrected deployed stylesheet and both script chunks matched the pinned
production build's filenames and bytes exactly. No generated output or cached
environment data is admitted to the source archive.

## HTTP catalogue migration

The deployed browser consumes the [news API](news-api.md), not MCP protocol.
The original HTTP-migration image's immutable source was
`076fc03305ab57f5f6ee91381bc9cc49d38a05d91bc8a9e873626c5f61f05005`.
The current image source is recorded under [Browser-local timestamps](#browser-local-timestamps).
Public config, both script chunks, stylesheet, detail SPA fallback and exact
owning ARM readback were verified. The regular-browser/cache gate remains open;
no automatic or manual sign-in evidence is invented.
Implementation `8f6ebf70e9921cbc7f3bbc0626e4515a2a1a7fb6` passed exact-source CI
`41465462841`. The subsequent README/runbook status publication is documentation
only; the deployed image retains its original implementation/source association.
Measured-status commit `51740af` passed separate CI `41466535819`; the remaining
regular-browser/API-cache/deployed accessibility gate stays open.
Runtime fields become tenantId/clientId/agentUrl/agentScope/newsApiUrl/newsScope.
The same delegated news.read audience and retained SPA consent are used;
UI_MCP_PERMISSION_ENABLED remains enabled because that registration is the shared
news API. The browser MCP SDK is removed; agent interaction/tools remain A2A/MCP.

UI_HTTP_API_ENABLED is an owning app-only preparation/Terraform/readback switch.
Its default-off branch preserves matching legacy config for old images. The new
image accepts HTTP config only, not automatic MCP fallback. HTTP mode requires
news enablement, retained permission and independent backend API readiness.
NEWS_ORIGIN/CSP and the static smoke checker must match the new configuration.
Never provision ui-identity or remove consent for this transport migration.

Browse pages contain up to 20 items. Load more is explicit, uses applied filters
and stops at 200 distinct displayed items; the cap is not server exhaustion.
Restart begins again with the same applied filters. Semantic search is bounded
to 20 without paging. Append errors retain existing cards and offer explicit
retry; Refresh/restart need not bypass the server's 60-second response cache.
Live pages can overlap/change membership and are not a durable snapshot.

`/news/<uuid>` shows stored summary, author/date origin/publisher categories/tags
and safe original links. Back/Forward restores transient browse state; direct
links work through the existing SPA fallback. Only a validated same-origin item
path is restored through explicit MSAL sign-in. URLs/history state never carry
questions, filters, tokens or article bodies; no app-managed persistent browse
store is added. Ordinary visited item URLs are intentional.

Ask about this opens the composer with the displayed ID and applied filters,
never submits automatically. Each running/completed answer keeps its submitted
context despite navigation. Sign-out aborts all reads and clears transient state.

After local checks, review only the immutable UI image/config/mode plan:

```bash
uv run --locked newsloom-platform build-ui
azd env set UI_HTTP_API_ENABLED true
uv run --locked newsloom-platform prepare-ui-layer
azd provision ui --preview
# Apply only after fresh owning-plan approval.
azd provision ui
uv run --locked newsloom-platform verify-ui
```

Keep actual image/config/permission/HTTP versus A2A evidence separate from authored
API fixtures and browser/axe tests. Missing regular-browser/API-cache/deployed
accessibility evidence stays open; never export credentials or request another
test-browser sign-in. A publication exception must be explicit for this slice.
Rollback restores the reviewed prior image and matching config mode, without
disabling the backend API or changing identities, grants, models or schedules.

## Reader feedback

Readers can rate the daily briefing (under the TL;DR) and each completed research
answer with **Helpful** / **Not helpful** and an optional comment of at most 1,000
characters. Their current rating is shown when the item is displayed, and rating
again replaces it. Rating an answer sends the question, answer, citations and
applied filters shown on screen; answers are otherwise not stored. Voting never
reads the briefing again or starts research. Feedback uses its own request lanes,
so it cannot block or cancel news and briefing reads.

The reviewer page at `/feedback` lists the latest rating per reader and item with
rating, type and date filters, and exports JSON Lines. Only object IDs in the API's
`FEEDBACK_REVIEWER_OBJECT_IDS` can use it; others see "You are not a feedback
reviewer." Readers are pseudonymous and feedback text is never logged; see the
[news API](news-api.md#reader-feedback).

## Architect radar

The signed-in home page (`/`) is the radar
([change](../openspec/changes/archive/2026-11-10-architect-radar-home/proposal.md)): the daily briefing as a header, whose
citation markers open their sources directly, then a strip of upcoming deadlines,
"Act now", "Worth knowing" (8 entries, then "Show more") and a collapsed "When
you have time". Each card shows its status or deadline, vendor, statement (linked
to the source), the triage reason and product links, with **Done**, **Snooze**
(7 days), **Follow** (adds the card's products to My stack) and **Ask** (opens the
agent panel with the item selected). Groups show four rows, then "Show all".
"Hidden (n)" lists done and snoozed cards with **Restore**; 7 or 30 days changes
the window.

The previous list moved to **All news** (`/news`); item pages keep `/news/{id}`.
**My stack** (`/stack`) searches vendors and products and lists followed ones;
product pages (`/products/{id}`) show the vendor, aliases, related products and
the timeline, which is also how product matching can be reviewed. Pages share the
existing keyboard, focus and axe checks on desktop and phone widths.

## Read-only overnight

When news API responses carry `X-Newsloom-Read-Only`, the app shows one line
under the header, "Read-only until 08:00 · data as of 23:45" (local times of the
next 07:00 UTC wake and of the snapshot), and hides search, the agent panel and
Ask buttons, feedback, card actions, follow toggles and stack editing (controls
marked `data-write`). A refused action shows "Not available while Newsloom is
read-only overnight." The line disappears with the first live response. See the
[operations runbook](operations.md#read-only-overnight).

## Research conversations

Owned by [`research-conversations`](../openspec/changes/research-conversations/proposal.md).
The agent panel shows the conversation as a thread (question, answer, sources)
with the composer below it; the newest answer scrolls into view, up to three
suggested follow-ups appear as buttons under it, and "New conversation" starts
over. Each question sends the last three turns as history (oldest answer text
trimmed first to 12 KiB) and accepts the agent's `conversation` artifact for
follow-ups and cited item IDs. The thread is kept in `sessionStorage` (this tab
only), re-validated on load and removed on sign-out. Rating applies to the latest
answer. Up to 1000px wide the panel is a full-height sheet over the news: Tab
stays inside it, Escape closes it and focus returns to the control that opened it.
