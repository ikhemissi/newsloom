# Design

## Context

See [proposal](proposal.md) for motivation and
[navigation contract](specs/browser-news-navigation/spec.md) for requirements.
Observed integration seams:

- NewsCatalog currently returns item arrays from recent/search and a source
  catalogue. McpCatalog owns SDK calls, Zod guards, two cancellation lanes,
  exact metadata checks and a 90-second/1-MiB boundary.
- App separates draft/applied filters and submitted query. List replacement
  drops stale reads, while submitted A2A context survives later browsing changes.
  There is no cursor, item-detail model or router.
- Runtime config is a strict six-field MCP/agent schema. MSAL selects news versus
  agent audience; login currently restores only `/`. UI platform/Terraform/CSP/
  smoke-check code derives MCP_ORIGIN from mcpUrl.
- Nginx already serves SPA fallback for non-asset paths, so `/news/<uuid>` needs
  verification but no new backend route.
- The deployed API has typed page/detail/discovery/search results, cursor-only
  continuation, safe errors and read/cache metadata. Its authenticated live
  acceptance remains open, not retroactively completed by authored UI tests.

The user selected detail pages, explicit Load more and a 200-item display cap.

## Goals / Non-Goals

**Goals:** Connect the existing API to the actual reader journey; retain the
domain seam, stable auth boundaries and immutable research context; make paging/
detail/history behavior explicit and independently testable.

**Non-Goals:** A second cache/query framework, replacement authentication, new
backend semantics, arbitrary client URLs, full article rendering, semantic
pagination or a persistent browsing/chat store.

## Decisions

### 1. HTTP-only catalogue behind the domain boundary

Replace McpCatalog with HttpCatalog at composition. Extend domain results with
typed `NewsPage` (items, next cursor and safe read/cache metadata), `NewsDetail`
and a detail lookup returning an explicit not-found result. Keep SDK/wire fields
inside the adapter; map stored names such as published_at to existing UI names.
Distinguish browse versus bounded semantic result modes, not a cursor on any array.

Use the configured trusted base only:

| Domain request | HTTP |
| --- | --- |
| initial/restarted latest or metadata browse | GET news, limit 20 and applied filters |
| Load more | same GET plus the returned cursor |
| explicit semantic search | POST search JSON, limit 20 |
| source choices | GET sources |
| item detail | GET news/{validated UUID} |

Never follow a response URL as a page endpoint. Validate cursor syntax/size as
opaque data and pass it only as an encoded parameter on the trusted news route.
Validate pages with at most 20 unique UUIDs, expected result mode, finite score
where semantic, and all metadata predicates. Validate detail's ID against the
requested UUID; keep item URLs as inert link data, not fetch authority.

Validate `meta.read_at` as aware time and cache age as finite/nonnegative.
Do not reject age above 60 solely on that number: an uncached slow read can
complete after cache admission expires. Explain bounded server reuse/live paging;
do not imply that Refresh bypasses the API cache or gives a durable snapshot.

Keep bounded news/catalogue lanes and add one cancellable detail lane. Each
operation's 90-second deadline includes token acquisition, fetch and body parsing,
with a 1-MiB response bound. Reuse/extract existing bounded fetch primitives where
possible, preserving A2A streaming/error/cancellation semantics. Fetch with
no-store, omitted credentials and rejected redirects; no automatic retry/fallback.
Map 401/403, 429 and 504 to existing fixed categories. Detail 404 is not-found;
404 on another API route is service/config failure. Add a news-specific fixed
400/input failure rather than reusing the question-length message. Never render
raw API errors/request IDs/body text as diagnostics.

Remove unused browser MCP SDK/imports and replace its protocol fixture with
an authored real-HTTP-API fixture. Retain all backend MCP protocol/auth tests
and A2A SDK tests. Remove the dependency with npm and preserve other lock pins.

Alternative: retaining both browser adapters encourages silent fallback and
duplicates contracts; new Axios/router/query-cache dependencies are unnecessary.

### 2. Explicit configuration migration, no identity mutation

New UI config is strictly:
`tenantId`, `clientId`, `agentUrl`, `agentScope`, `newsApiUrl`, `newsScope`.
newsApiUrl must be canonical credential-free HTTPS ending `/api/v1` without
query/fragment; newsScope is the existing API audience's delegated news.read.
Keep its audience distinct from the SPA and agent. Do not retain mcpUrl aliases
or runtime adapter negotiation in the new browser.

Add default-off UI_HTTP_API_ENABLED in the owning UI layer/preparation/readback.
When enabled, derive newsApiUrl from the retained MCP resource's HTTPS origin,
emit the new config and NEWS_ORIGIN/CSP binding, and require UI_NEWS_ENABLED plus
the already-owned news permission. Before rollout, independently verify that the
retained MCP app's API flag/origin/image/configuration are ready; checking only
an ignored environment variable is insufficient.

The disabled preparation branch preserves the historical four/six-field config
for matching old images; it is not supported runtime fallback in the new image.
Keep UI_MCP_PERMISSION_ENABLED and its existing identity/consent ownership intact:
the registration remains the shared news API even after its browser SDK is removed.
Do not provision ui-identity, remove consent, change backend origins or deploy MCP.
Update static entrypoint/header templates, smoke checker and exact UI ARM readback
together so new/legacy image/config combinations cannot be silently mixed.

Rollback restores the retained prior UI image and matching config mode through a
fresh reviewed owning plan/source binding. It must not disable the backend API,
erase identity state or select MCP automatically after a fetch failure.

### 3. Page state belongs to an applied browse epoch

Keep draft/applied state semantics. A browse epoch owns applied filters, submitted
query, item list, continuation and accepted continuation history. Changing draft
controls does not replace that epoch. Search/Apply/Reset/Clear/Refresh explicitly
start the correct first page, abort old work and discard its continuation.

Load more is available only in metadata/newest-first mode with a continuation,
no pending append and fewer than 200 distinct displayed items. Send the original
epoch's filters/page size, not current drafts. Append new IDs in server order,
retain already-visible versions of overlapping IDs until refresh and disclose
that live updates can overlap/change membership. Reject repeated/nonadvancing
cursors, malformed page shapes or a page contradicting the applied filters.
Do not fetch another page automatically to fill gaps or compensate for overlap.

Append failure retains prior cards and continuation with a separate visible
error/retry action; stale completions cannot modify a newer epoch. At 200 items,
stop fetching and show the user-selected display cap separately from server
exhaustion. Restart uses the same applied filters and resets to the first 20.
Semantic search remains top 20 in relevance order, with no Load more. Neither a
cap nor missing continuation is an exhaustive archival/snapshot claim.

Alternative: OFFSET, implicit prefetch or unbounded list growth contradict the
chosen API/UX contract. Virtualization is unnecessary for the selected 200 cap.

### 4. Native shareable detail routes, transient browse restoration

Use a small typed route model and native History API/popstate, not a new router.
Only `/`, `/news/<uuid>` and the existing auth bridge have application meaning.
Malformed/unknown links show a distinct local invalid/not-found state without
fetching arbitrary paths. Normalize validated UUIDs; do not encode search text,
filters, tokens, questions or article fields in URLs/history state.

Opening a card detail pushes the item route, preserves the in-memory browse epoch
and scroll position, and fetches exact detail. Detail replaces the news-column
content, leaving the optional agent panel independent. Show stored summary,
source/category/time, author/date origin/publisher categories/tags, safe original
link and Ask about this. No remote article/image fetch or HTML interpretation.

Back to news/browser Back restores the existing list/cursor/filter/scroll state.
Forward can reload exact detail without A2A replay. A direct detail URL has no
manufactured list snapshot; returning initializes normal news. Search or applying
new browsing constraints exits detail into the correctly reset list; draft-only
edits do not fetch. Detail loading, 404, malformed response and transport/auth
failures remain separate, with explicit recovery.

Adjust MSAL redirectStartPage only to restore a validated same-origin detail path
or `/`. Keep `/auth/callback`, sessionStorage and no automatic question resend.
Sign-out clears all React detail/list/cursor/context state and returns to root;
old browser history entries must never restore data without sign-in. Ordinary
visited route URLs are intentional; no app-managed persistent browse history or
article-bearing history state is introduced.

### 5. Agent context and accessibility remain independent

Ask about this from a card/detail selects the exact displayed item and opens
the composer, never sends. Continue showing applied filters separately from each
submitted immutable item/filter snapshot. Do not broaden filters to fit an item,
append article/query text as hidden instructions, or relabel old answers after
navigation. Existing active-research selection protections and Stop remain.

Paging, opening detail, returning and closing the panel must manage focus to a
connected opener or appropriate heading/control, not a detached item element.
Announce append/detail loading/errors. Keep the viewport-bounded independently
scrollable panel, lofi/dark toggle, keyboard citations and narrow-screen layout.
Sign-out/unmount abort all three read lanes and reject late results.

### 6. Measured delivery and unresolved live evidence

Update the owning PRD/ADR/UI/API runbooks during implementation. State that this
transition supersedes earlier as-delivered MCP transport wording; do not rewrite
historical receipts, check old acceptance boxes, or archive contradictory browser
contracts together without reconciliation.

Run real API adapter contracts, component/state tests, MSAL redirect regressions,
deep-link static-container checks and browser/axe cases, then the primary gate
and packages on the exact selective tree. Build/review/deploy only UI image/config/
transport-mode changes in retained state; verify API/MCP/A2A images, consent,
workload identities and schedules remain unchanged.

Verify the real regular-browser HTTP request journey, cache-age/hit versus
semantic-miss behavior, paging/details and explicit A2A context with safe outcomes/
counts only. There is still no tool access to the user's existing regular-browser
session. Do not export credentials, request another test-browser sign-in or invent
automation proof. Leave missing checks open and seek a new explicit exception
before publishing around them; prior API/UI exceptions are not automatic approval.
Preserve all evaluation receipts and defer evaluation execution until this UI
migration's owning delivery is addressed.

## Risks / Trade-offs

- More navigation state -> typed browse epochs/detail IDs, independent cancellation
  and Back/Forward/stale-result tests rather than a global state framework.
- Cross-page live changes -> deduplicate visible IDs, disclose overlap/live
  semantics and require explicit refresh instead of promising stable snapshots.
- New image/old config mismatch -> strict new schema and reviewed mode-bound
  image/config rollback, with no runtime transport fallback.
- Browser acceptance limitations -> actual regular-browser evidence where
  available, explicit unchecked tasks elsewhere, no credential/test-browser workaround.
