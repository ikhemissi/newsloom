# Spec Delta

## Purpose

Provide authorized HTTP access to stored news with bounded response reuse and
honest browsing cursors, without changing MCP tools or agent interaction.

## ADDED Requirements

### Requirement: Versioned read-only HTTP news access
The service SHALL expose `/api/v1/news`, `/api/v1/news/{id}`,
`/api/v1/sources` and `/api/v1/search` with typed JSON contracts. Only stored
public news fields SHALL be returned. Detail MUST NOT expose raw articles,
vectors, private processing state or workload configuration.

#### Scenario: An authorized reader browses or discovers filters
- **WHEN** GET news or sources succeeds
- **THEN** news returns `items`, `next_cursor` and `meta`, or discovery returns
  `sources`, `categories` and `meta`, respectively
- **AND** default news browsing has no date cutoff, uses a default limit of 20,
  and preserves newest-publication-first ordering with ascending ID ties
- **AND** source/category discovery uses exact stored IDs and supplied labels

#### Scenario: A stored item is requested
- **WHEN** GET detail uses a valid stored news UUID
- **THEN** the response contains `item` and `meta`, with the existing public
  projection plus stored author, date origin and publisher categories
- **WHEN** that UUID is absent or identifies only queue/quarantine work
- **THEN** the response is an explicit 404 without exposing processing state
- **AND** malformed UUIDs are 400 input errors, not not-found successes

### Requirement: Authorization before every cache access
Every API data request SHALL verify signature, trusted tenant/issuer, audience,
lifetime and delegated `news.read` before cache lookup, repository or model work.
Cache reuse MUST be partitioned by verified caller and authorization context.
No token or credential SHALL be stored in a response-cache key or value.

#### Scenario: A cached result exists but authorization is absent or invalid
- **WHEN** a caller presents a missing, forged, expired, wrong-tenant,
  wrong-audience or otherwise invalid token
- **THEN** the request returns 401 before even inspecting the response cache
- **WHEN** a verified token lacks delegated `news.read`
- **THEN** the request returns 403 before cache, repository or model work
- **AND** app-only tokens and agent-audience tokens cannot substitute

#### Scenario: Callers request identical public data
- **WHEN** two different verified callers submit identical valid requests
- **THEN** their cache partitions remain distinct and both are independently
  authorized, even though the current readable news corpus is shared
- **AND** token renewal for the same verified caller does not require token-
  keyed caching; a changed scope/client/policy context cannot borrow an entry

### Requirement: Existing filter and semantic ranking fidelity
HTTP filtering SHALL retain exact source/category IDs, ALL-tags semantics and
UTC-aware inclusive `from`/exclusive `to` boundaries. Semantic search SHALL
apply every filter before exact cosine ranking with ascending ID ties.
Metadata-only operations MUST perform zero inference; semantic failures MUST
NOT fall back to metadata results or another model.

#### Scenario: A reader applies metadata filters
- **WHEN** GET news supplies any supported combination of source, category,
  tags and publication bounds without a query
- **THEN** all returned rows satisfy every constraint with zero embedding/chat calls
- **AND** an unmatched valid source/tag/combination yields an explicit empty page

#### Scenario: A reader explicitly searches by meaning
- **WHEN** POST search contains a nonblank query and optional metadata filters
- **THEN** at most its requested 1-50 items are relevance-ranked within those filters
- **AND** the existing validated embedding deployment/vector contract is used
- **AND** `next_cursor` is null and `meta.result_scope` is `bounded`, not an
  assertion that all matches were returned
- **AND** no arbitrary similarity cutoff, lexical substitution or generation occurs

### Requirement: Precise newest-first continuation
Browsing SHALL use keyset continuation over publication descending and ID
ascending, preserving all normalized filters and page size. Cursors SHALL be
versioned, bounded and validated as data, never authority or SQL. Semantic search
SHALL reject cursors. Live traversal MUST NOT claim a durable database snapshot.

#### Scenario: Multiple news items have the same publication timestamp
- **WHEN** an authorized reader follows every returned cursor over unchanged data
- **THEN** eligible rows are neither skipped nor duplicated at timestamp ties
- **AND** the last page has `next_cursor: null`; an exact page-size multiple
  does not produce a false extra page

#### Scenario: A continuation is invalid or reused under different filters
- **WHEN** a cursor is malformed, oversized, unsupported, or bound to a different
  normalized filter/page-size fingerprint
- **THEN** the API returns 400 before cache, repository or model work
- **AND** cursor contents cannot select a table, endpoint, caller identity or model

#### Scenario: The news corpus changes between pages
- **WHEN** ingestion or authorized corrections change records during traversal
- **THEN** each page reflects its bounded-age read, with live keyset semantics
- **AND** the contract discloses that newer insertions require a fresh first page
  and updates/deletions can change traversal membership; no snapshot completeness
  or semantic pagination is fabricated

### Requirement: Bounded private response caching
The API SHALL use process-local response caching with a non-sliding maximum
60-second lifetime, bounded entries/bytes and no durable storage. Cache hits MUST
avoid repository and embedding calls, never bypass authorization, and never
refresh expiry. Errors, credentials, conversations and query vectors MUST NOT
be cached. Responses SHALL be `Cache-Control: no-store`.

#### Scenario: An identical authorized request repeats
- **WHEN** a validated successful response exists in the same caller partition
  before its absolute expiry
- **THEN** the cached public payload is reused without repository/model calls
- **AND** response metadata identifies its data read time and bounded cache age
- **AND** touching the entry does not extend its original expiry

#### Scenario: News changes or a cache entry expires
- **WHEN** a successful result is reused within the lifetime
- **THEN** up to 60 seconds of response reuse is explicitly permitted
- **WHEN** the entry expires, is evicted, or the process restarts
- **THEN** the next authorized request performs a fresh read
- **AND** failed refresh never serves stale data or a success-shaped empty fallback

#### Scenario: The app has separate workers or revisions
- **WHEN** requests reach different processes or deployment revisions
- **THEN** each cache is independent and disposable, with no cross-replica
  consistency, invalidation or hit-rate guarantee
- **AND** cache size/oversized-entry handling remains bounded without truncating data

### Requirement: Explicit bounded failures and cancellation
API execution SHALL share finite MCP work capacity, with bounded admission,
deadlines, request/response sizes and cancellation. Invalid inputs MUST cause no
repository/model work. Errors SHALL contain only a fixed safe code and opaque
request ID, never raw exception text or echoed input.

#### Scenario: A request violates its contract
- **WHEN** a caller supplies unknown/duplicate scalar fields, invalid limits,
  blank queries, unsupported content types or malformed dates/bodies
- **THEN** it receives the documented 400/413/415 response as appropriate
- **AND** unsupported route methods receive 405, not a redirect or replay

#### Scenario: Infrastructure or capacity cannot complete work
- **WHEN** admission is exhausted, a deadline expires, or storage/model/key
  infrastructure is unavailable
- **THEN** the API returns a documented 429/504/503 failure, without cached errors
  or fabricated results
- **WHEN** a client disconnects or cancels
- **THEN** unfinished work is cancelled, resources released and no partial result
  is cached; semaphore release is verified on every termination path

### Requirement: Explicit API browser and telemetry boundaries
API routes SHALL enforce exact host/origin/method controls independently of MCP
SDK route protection. Allowed preflight MUST perform no authentication, cache,
repository or model work. Logs and observations MUST use fixed route/outcome/cache
categories and counts/timings, never URLs with inputs, identities or content.

#### Scenario: A browser calls the API
- **WHEN** an approved exact-origin browser uses GET news/detail/sources or POST search
- **THEN** allowed responses, including safe errors, have readable exact-origin CORS
- **AND** preflight admits only the route's supported method and fixed headers,
  with no credentials, wildcard origin or method broadening
- **WHEN** the origin is duplicate/unapproved or the host is invalid
- **THEN** the request is denied before authorization/cache/data/model execution

#### Scenario: Queries and publisher fields contain private canaries
- **WHEN** success, cache hit, invalid input, dependency error or cancellation
  is observed through application and dependency telemetry
- **THEN** those canaries, bearer tokens, claims, cursor contents, request/response
  bodies and raw exception text are absent
- **AND** hit/miss, repository and embedding call counts can still be measured

### Requirement: Compatible measured co-hosted delivery
The API SHALL deploy in the retained MCP app with its existing workload identity,
permissions, model and capacity profile. Existing MCP/A2A/UI behavior MUST remain
compatible. Acceptance SHALL distinguish local fixtures, deployed checks and
regular-browser observations; missing evidence MUST remain open.

#### Scenario: The API slice is deployed
- **WHEN** local gates and a reviewed immutable MCP-only image/enablement plan pass
- **THEN** owning readback verifies API enablement, image, origin, identity and
  unchanged backend apps/schedules/data authority
- **AND** native MCP and existing UI MCP calls still work; the UI has not yet
  switched transport and agent interaction remains A2A

#### Scenario: Required deployed verification is unavailable
- **WHEN** regular-browser tooling, delegated authorization or live parity evidence
  cannot satisfy an acceptance task
- **THEN** the limitation is reported and the task remains unchecked
- **AND** no separate test-browser sign-in, credential export, evaluation replay,
  automatic acceptance exception or archival bypasses that limitation
