# Tasks

Checked tasks have verified local/Azure/user evidence; exact-commit CI and
delivery close-out remain pending.
Follow [the design](design.md),
[the serving contract](specs/mcp-serving/spec.md), and
[the search contract](specs/news-search/spec.md).
Local checks precede cloud changes. Real retrieval measurements, cleanup and
browser sign-in must pass before this slice is declared complete.

## 1. Public contracts and read-only news queries

- [x] 1.1 Implement the four typed tool inputs/results with the approved limit, UTC interval, all-tags and category-ID semantics. Verify exact JSON tool names/aliases including `from`, structured output shapes, missing versus malformed IDs, represented source/category discovery and rejection of booleans/out-of-bound fields with focused tests. Document public field/result/error shapes and defaults in the MCP runbook, linking to the existing category catalogue.
- [x] 1.2 Add the additive MCP read migration and fixed repository projection without editing earlier migrations. Verify replay, preservation of existing data and actual local role denials for queue/quarantine reads, news writes, DDL and other workload roles; test recent/detail/discovery queries and current committed visibility. Document the permanent column grants and distinguish public result fields from internal vector/model fields.
- [x] 1.3 Implement parameterized metadata filters and exact cosine ranking over the materialized eligible relation. Verify selective-filter traps, date boundaries/offset normalization, tag containment, deterministic ties, returned scores, sufficient-result cardinality and no global-top-k-then-filter path with real local PostgreSQL. Document why the existing HNSW index is retained but not used for this initial correctness-first path.

## 2. Authentication and isolated workload inference

- [x] 2.1 Resolve/pin stable MCP SDK, ASGI and JOSE dependencies compatible with Python 3.15 and the installed VS Code harness, including isolated no-dev package startup. Implement tenant-bound JWT verification, protected-resource metadata and challenges. Verify signature/algorithm/issuer/audience/lifetime/scope failures, unknown-key refresh/unavailability, ID/app-only token rejection and no token-directed URL retrieval using actual HTTP tests with ephemeral local signing keys. Document audience-versus-resource URL and secretless sign-in configuration.
- [x] 2.2 Implement the owning registration inventory/adoption/preview flow and azd identity layer for a single-tenant API scope and pre-registered public PKCE client. Verify mocked idempotence, exact scope/redirect changes, no display-name guessing, no credential creation and ignored-only identifier outputs. Document required operator permissions/consent and the installed-harness callback preflight; stop for an explicit decision if a proxy, secret, wider grant or unsupported callback would be required.
- [x] 2.3 Reuse/extract the bounded embedding transport and vector validation in core without changing enrichment's behavior. Add the typed query-embedding path under the MCP identity. Verify unchanged enrichment adapters/serialization, no generation call, no user-token forwarding, model/version compatibility and finite nonzero 1536-dimensional response/deadline/Retry-After/error handling. Document operational failures and shared-quota behavior without semantic-to-metadata fallback.

## 3. Protocol runtime and owning deployment

- [x] 3.1 Wire all four tools into the SDK Streamable HTTP app with authorization before tool/data/model work, canonical routing, bounded bodies/concurrency/timeouts and cancellation. Verify real HTTP negotiation/discovery/calls, unauthorized initialization/list/calls, exact input/output schemas, invalid Host/Origin, redirects, overload and cancellation; in-memory client tests alone are insufficient. Document stateless behavior, health/readiness boundaries and untrusted returned content.
- [x] 3.2 Add the MCP Dockerfile, immutable registry build/operator helpers and owning ACA app azd/Terraform layer after identity/migration inputs. Verify isolated image startup, source/catalogue hashing, one always-on replica, health probes, HTTPS ingress and fail-closed auth/resource configuration with focused helper/mocked-provider tests. Document preview/adoption/deploy/rollback, actual endpoint discovery and the fact that existing pipeline jobs/schedules/data remain unchanged.
- [x] 3.3 Add authenticated tool/search latency, outcome and model-usage telemetry with export allowlists and safe dependency/framework logging. Verify canaries across actual HTTP success, invalid input, authentication failure, SQL/model failure, cancellation and automatic SDK spans; prevent query/body/article/token/request-ID capture. Document safe metrics/categories, delayed evidence ingestion and no fabricated empty-success responses.

## 4. Frozen retrieval evaluation and local acceptance

- [x] 4.1 Add an authored corpus and 20 frozen relevance cases (ten filtered, ten unfiltered), with separate development examples. Implement evaluation-only shared-query execution and exact-named isolated-schema preparation/cleanup using the retained migration authority and temporary MCP SELECT only. Verify denominators, recall@5 group means, zero-filter-violation gates, malformed/missing-case failure, SQL parity and cleanup on success/failure/interruption; public tools must not accept schema/relation selection. Document private evidence and temporary-grant removal.
- [x] 4.2 Run focused contract/auth/protocol/database/inference/privacy/operator tests, then `bash scripts/check.sh` with explicitly disposable local PostgreSQL and `uv build --all-packages`. Verify strict types, dependency/provider locks, package-only startup and all current ingestion/enrichment regressions, retain measured results, and stop the disposable database. Normal tests must not need cloud credentials or real model calls.

## 5. Reviewed Azure and end-user acceptance

- [x] 5.1 Preserve resource/news/schedule baselines privately and verify actual registration/consent permissions, deployed embedding contract/quota, SDK interoperability and metered costs. Review native identity/migration/app previews and apply only the owning additions/adoptions in the existing environment. Verify immutable image, actual URL/audience/scope, health/host/origin controls and stable shared IDs/identities/schedules without broader grants or model-capacity changes.
- [x] 5.2 Exercise real news reads, embedding access, and forbidden queue/quarantine/write/admin operations under the actual MCP identity. Verify independent read-only result/identity checks and HTTP missing/forged/expired/wrong-tenant/wrong-audience/wrong-scope failures without data/model access or token logging; retain actual denial evidence rather than permission inventory alone.
- [x] 5.3 Prepare the approved temporary evaluation schema, run the frozen study under the real MCP identity through the shared embedding/SQL ranking path, and retain all per-query IDs/scores/fingerprints and group counts. Verify recall@5 >=0.80 independently for each ten-query group, zero filter violations, no missing/error cases and verified removal of the exact schema/grant. Failure or incomplete cleanup blocks acceptance; do not seed production news or relabel cases to pass.
- [x] 5.4 Connect the deployed endpoint from the installed VS Code harness using the private pre-registered OAuth client configuration. Complete actual Entra browser sign-in and invoke all four tools, including metadata-only and semantic filtered search; verify source/category/date/tag/result/ID correctness against independent stored-news checks and authenticated telemetry. Keep the task unchecked until the real user flow succeeds; a scripted token call, health check or provisioned URL is not a substitute.

## 6. Persistent delivery evidence

- [ ] 6.1 After local, Azure, retrieval and end-user acceptance, commit/push the implementation with the required trailer and verify CI for its exact SHA. Record the actual workflow outcome and preserve the evaluated image/configuration reference without amending away verified evidence.
- [ ] 6.2 Update the owning runbook, phase/capability/ADR status and this change's acceptance evidence with actual results, limits and unchanged pipeline/quarantine behavior. Verify local links, safe committed content and final-head CI for any separate evidence commit; leave every unverified task unchecked and do not claim full PRD-1 acceptance.

## Workflow follow-up

- Present the completed evidence for review before archival.
- Archive/sync this change and the already completed enrichment change only when
  requested through their respective workflows.
- Phase-wide tests/evaluations remain Step 1.6, not automatically complete because
  these tools are deployed.

## Acceptance evidence

### Local implementation and read-only preflight, 2026-10-24

- `bash scripts/check.sh` with explicitly disposable PostgreSQL 18/pgvector:
  **407 passed, one opt-in live-publisher test skipped**; strict mypy passed
  for 77 source files; Ruff, lock/identifier/feed/OpenSpec checks passed;
  all seven Terraform roots validated and **24 mocked-provider tests passed**.
- `uv build --all-packages`: all five wheels and source distributions built.
  The isolated no-dev MCP image imported the actual SDK/service as UID 65532,
  included both required configuration files, and rejected missing configuration
  with a sanitized failure. This is local image evidence, not deployed health.
- Actual HTTP/ASGI tests exercise SDK negotiation, schemas, authorization,
  chunked/non-chunked body bounds, workload cancellation and overload.
  Ephemeral signing keys prove negative access-token cases. Canary checks cover
  SDK spans and logs on success, invalid input, authentication, SQL/model failure
  and cancellation, including removal of client trace-state strings.
- Deterministic embeddings and real local SQL passed retrieval mechanics with
  both fixed ten-case denominators and zero filter violations. Six filtered
  cases have more than five eligible candidates. These are not measured
  real-model recall. Operator tests reject contradictory per-case/summary
  evidence and verify cleanup even on preparation failure or interruption.
- One intermediate concurrent-build run failed the existing timing-sensitive
  ingestion-concurrency assertion (observed peak two, expected four). The
  focused rerun and final full gate passed; ingestion behavior was not changed.
  The disposable database was then stopped.
- Read-only registration inventory found no selected existing API/public client.
  Native `azd provision mcp-identity --preview --no-prompt` proposed **five
  additions, zero changes, zero deletions**. Tenant policy allows default-user
  app creation; actual creation permissions and interactive consent remain
  unproven until exercised. No directory/resource changes have been applied.
- Private Azure baselines retain shared identities/resources, both unchanged
  `*/30 * * * *` schedules, and the successful existing Standard embedding
  model/version. No model capacity was changed. Actual live news baseline,
  migration/app previews, deployment, workload denials, real retrieval,
  telemetry readback, browser PKCE sign-in and exact-commit CI remain unchecked.

### Approved identity apply and service previews, 2026-10-24

- After explicit review/approval, native `azd provision mcp-identity --no-prompt`
  applied **five additions, zero changes, zero deletions**. Exact post-apply
  inventory verified both applications/principals, the single delegated scope,
  approved public callbacks and credential absence. Actual IDs remain ignored.
  This proves registration creation, not browser consent or tool access.
- A post-apply native identity preview reports **no changes**. Independent
  Graph readback also verified zero passwords/certificates on both applications
  and both service principals.
- The MCP and migration images were built successfully in the existing registry
  from the same verified source-input fingerprint; immutable references are
  retained privately. No ingestion/enrichment image was rebuilt or deployed.
- A read-only execution under the existing migration identity measured **836
  news/completed**, 1,135 pending and two dead-letter items, with zero invalid
  vectors, completion mismatches, duplicate URLs/GUIDs or published rejections.
  All 23 quarantined entries remain retained. This is a concurrent pipeline
  snapshot, not a claim that these counts stop changing.
- A first console query used only the legacy log table and failed. Reusing the
  repository's documented dual-table query retrieved the successful existing
  readback without rerunning the job or changing resources.
- Native migration preview: **zero additions, one in-place change, zero
  deletions**, changing only the migration job's immutable image.
  Native app preview: **one addition, zero changes, zero deletions**,
  creating the HTTPS MCP app with one 0.25-vCPU/0.5-GiB replica.
  Neither preview has been applied; the migration grants only news-column SELECT.
- Both existing job IDs, identities, configuration/schedules, images and
  templates still match the private preflight baseline exactly.
  An incidental native-preview upgrade of the old migration provider lock was
  removed; no unrelated provider upgrade is included.

### Approved service deployment and real retrieval, 2026-10-24

- Explicit approval preceded native migration/app apply. Migration apply updated
  only the existing job image and its post-provision execution succeeded.
  App apply added one resource, changing/deleting none. Actual readback matched
  its immutable image, existing MCP identity, canonical hostname and one-replica
  configuration. Liveness/readiness both returned 200; protected-resource
  metadata matched the configured resource/scope; anonymous discovery returned
  401 with a discovery challenge.
- The frozen study ran through the existing controller under a terminal wrapper
  because Azure CLI replica exec requires a TTY in this harness. No permanent
  evaluation worker, public debug endpoint, secret or wider permission was added.
  The controller retained all **20** cases with relevance/retrieved IDs and scores
  in ignored private evidence and verified exact-schema cleanup.
- **Unfiltered: 10 cases, mean recall@5 1.00. Filtered: 10 cases, mean recall@5
  1.00. Zero errors, zero filter violations**, and every individual recall was
  1.00. The authored fixture fingerprint was unchanged before/after inference.
  This is real-model evidence, unlike the earlier deterministic-vector tests.
- Live initialization/discovery/call probes rejected missing credentials and
  untrusted synthetic signatures with 401. Synthetic expired/tenant/audience/
  scope variants also had untrusted signatures; these are fail-closed boundary
  evidence, **not isolated live claim-validation evidence**. Trusted-signature
  claim isolation is covered locally; real delegated user sign-in is pending.
- Separate inline native-console diagnostics for live news and forbidden
  operations encountered terminal/exec transport failures and produced no
  accepted verification result. Task 5.2 remains unchecked. The API still
  returned liveness/readiness 200 and its active revision was healthy afterward.
  A narrow packaged verification command is the proposed next step; no denial
  or end-user acceptance is inferred from health or the retrieval study.

### Approved packaged verification CLI, 2026-10-24

- The user approved packaging the operator-only `verify-access` command and
  `verify-mcp` helper, without public tools/endpoints, new resources, grants,
  startup actions or schedules. It replaces the failed inline-console method.
- Revalidated with disposable PostgreSQL: **429 Python tests passed**, one
  opt-in publisher test skipped; strict mypy passed for **79 source files**.
  Ruff, identifier/feed/lock/OpenSpec checks, seven Terraform validations and
  **24 provider tests** passed. All five package wheels/sdists built.
  Regression tests prove unexpected write/DDL permission is rolled back before
  failure, ACL denial is not masked by READ ONLY, and HTTP 400/404/unavailability
  are not accepted as authorization denial. The disposable database was stopped.
- Native preview/apply changed only the existing MCP image: **zero additions,
  one in-place update, zero deletions**. Actual image readback matched the private
  immutable reference; serving source inputs and fixture fingerprints are
  retained privately. Pipeline job IDs, identities, templates, images and both
  schedules still match the preflight baseline exactly.
- The packaged verifier passed under the actual MCP identity: **926 news rows**,
  five independently matched recent IDs, detail/storage/discovery/metadata/
  semantic checks, **ten SQL denials**, allowed 1536-dimensional embedding,
  **two model-endpoint denials**, anonymous 401, a signed wrong-resource token
  rejected with 401, and **three signed Newsloom-audience app-only requests
  rejected with 403** for absent delegated scope. No raw records or tokens
  were emitted; no production fixture or permission was added.
- Frozen retrieval repeated on this exact image: **ten filtered and ten
  unfiltered cases, both mean recall@5 1.00**, zero errors/filter violations.
  The fixture fingerprint was unchanged. All per-case IDs/scores remain in
  private evidence; a subsequent verifier independently confirmed the latest
  evaluation schema absent.
- Added the `newsloom-dev` HTTP/OAuth entry through the supported VS Code CLI.
  Its URL/client match and persistence in the private user profile were checked.
  There are no static bearer tokens or secrets in this entry. Actual browser
  sign-in, delegated client calls, authenticated telemetry readback and
  exact-commit CI remain pending; they are not inferred from operator checks.
- The first user startup attempt did not open authorization and its standard
  Output channel stayed empty. Correct profile structure/URL/client were
  rechecked; Windows HTTPS and both backend health checks returned 200.
  Agent-host diagnostics show starting/stopped lifecycle and
  `not_configured (stopped)`, with no accepted browser/tool connection.
  Refreshing the active VS Code/Copilot session is the next diagnostic step;
  no authentication setting, permission or service configuration was weakened.

### Actual VS Code callback correction, 2026-10-24

- After refresh, the browser reached Entra but reported `AADSTS50011`: the
  observed client callback was `http://localhost` on an ephemeral port, not the
  initially inspected fixed `127.0.0.1` example. The actual registration readback
  confirmed the missing localhost callback. This corrects the preflight
  assumption rather than treating the earlier prompt text as actual flow proof.
- Microsoft documents port-independent matching for localhost redirect URIs.
  The user explicitly approved adding exactly `http://localhost` to the
  public/native client, retaining both original callbacks. No wildcard,
  per-port URI, secret, proxy, wider scope or consent grant was introduced.
- Focused local checks: **26 identity tests and five mocked Terraform tests**
  passed; strict typing (79 source files), Ruff, Terraform format/validation,
  identifier guard and strict OpenSpec validation passed.
- Native preview/apply changed only the public client's redirect list:
  **zero additions, one in-place update, zero deletions**. Post-apply Graph
  readback confirmed the added callback, retained original callbacks, same
  application/object identity, same audience/required scopes and zero credentials.
  No app image, migration, model deployment or pipeline job was changed.
- The user must start a fresh sign-in attempt; the original failed authorization
  URL is not acceptance evidence. Browser completion, tool use and authenticated
  telemetry remain unverified.

### Resource-indicator correction after browser sign-in, 2026-10-24

- The user reported browser sign-in success but continued MCP authentication
  prompts. Sanitized client diagnostics identified **`AADSTS9010010` /
  `invalid_target`** during token acquisition, not accepted MCP authorization.
  The canonical HTTPS resource was missing from the API's identifier URI list.
- Microsoft's MCP/Entra guidance documents registering that exact canonical
  URL on the same v2 API as the requested scope. The user explicitly approved
  this single identifier addition while preserving the original `api://`
  identifier, scope ID/name, client identities and GUID audience validation.
- The owning Terraform layer now creates/adopts the exact URL alias after the
  app URL is available. Inventory accepts only the configured URL plus the
  original identifier; unapproved aliases and missing base identifiers fail.
  No auth proxy, secret, scope expansion or serving-code change was introduced.
- **95 focused identity/auth/HTTP tests**, strict typing for 79 source files,
  Ruff, Terraform format/validation, **seven mocked identity tests**, strict
  OpenSpec validation and the identifier guard passed.
- Native preview/apply added only one `azuread_application_identifier_uri`:
  **one addition, zero changes, zero deletions**. Graph readback verified the
  exact alias, retained original URI, same API object/client/scope identities,
  v2 tokens and zero credentials. Exact adoption inventory passed and both
  existing service health checks remained 200. No serving image or job changed.
- Browser success still does not establish token acquisition or tool access.
  A new VS Code authorization attempt and all-four-tool verification remain
  required; tasks 5.1/5.4 and delivery remain unchecked.

### Actual native client tool calls after identifier correction, 2026-10-24

- The user reported restarting VS Code. The live harness then exposed all four
  Newsloom tools. Actual native client calls succeeded for recent news, source/
  category discovery, detail, metadata-only filtered search and semantic
  filtered search. This was not a manually supplied bearer token or health probe.
- Both searches combined source/category, two required tags and date bounds.
  The item published exactly at the inclusive lower bound was returned by
  browsing, detail and both searches. Metadata similarity was null; semantic
  similarity was finite (approximately 0.6818). No extra public field appeared.
- Authenticated Application Insights readback contained successful spans for
  all four allowlisted tools, including two search calls. Numeric HTTP/tool
  metrics were present; some aggregate/token metrics had not yet caught up.
  No query, article text or token was included in this recorded evidence.
- Final independent post-sign-in database verification and delivery close-out
  remain pending while the user restarts the client. Existing service/identity
  verification and earlier real-model retrieval evidence are retained.

### Warning-free migrated client and final acceptance, 2026-10-24

- The user explicitly approved moving only `newsloom-dev` from the Windows
  VS Code profile to the WSL Copilot private user configuration. The installed
  client migration mapping preserves the public client as `oauthClientId`
  under `mcpServers`, unlike the legacy nested `oauth.clientId` forwarded
  incompletely to Copilot. The destination was verified before removing the
  duplicate source entry; permissions are 0600 and no token/secret was copied.
  User confirmation after reload: all four tools visible, no warnings.
- Final actual migrated-client calls succeeded for recent/detail/discovery,
  metadata search and semantic search with source/category, two ALL tags and
  inclusive/exclusive publication bounds. The same stored ID appeared at the
  inclusive lower boundary, metadata similarity was null and semantic
  similarity approximately 0.6818. These were real harness calls, not a static
  bearer token or an operator-only substitute.
- Independent packaged workload verification passed again: **1,103 news**,
  five recent IDs independently matched to SQL, stored detail fields and
  represented source/category associations checked, filtered semantic search,
  ten actual SQL denials, two model denials, signed wrong-resource 401 and
  three signed app-only 403 responses. The latest exact evaluation schema was
  independently absent. Counts are a concurrent pipeline snapshot.
- Authenticated Application Insights readback for the final client window
  contained successful spans for all four tools (two recent, one detail, one
  discovery and two searches), tool/HTTP latency metrics and nonzero embedding
  call/token metrics. Only safe names/counts were retained, not article or token
  data; cumulative/gauge samples are not interpreted as per-request token sums.
- Actual app readback still matches the evaluated immutable image, existing
  identity, canonical URL and one-replica setting. Both existing pipeline
  jobs' IDs, identities, configuration/schedules, images and templates match
  the original private baseline. No quarantine/dead-letter item was released.
- Live anonymous and unapproved-Origin-without-token requests returned 401;
  an unapproved Host returned 404 at ingress. The fixed deployed Origin
  allowlist was checked; isolated authenticated bad-Origin behavior is proven
  by local HTTP tests, not inferred from an authentication-first live rejection.
- Final `bash scripts/check.sh` with disposable PostgreSQL 18/pgvector:
  **492 passed, one opt-in publisher test skipped**, strict types for 79 files,
  Ruff/feed/identifier/lock/OpenSpec gates, seven Terraform roots validated,
  **29 mocked-provider tests passed**. All five wheels/sdists built and the
  disposable database was stopped.
- Evaluated image-input fingerprint:
  `28da07d8ff5a686a346464d9c7759e04c7483326475cd7c03daabee30b3efa5a`.
  Frozen fixture fingerprint:
  `01ee167f7d0dab2aa58a7a1285a40d00a321ab31870851eb0843ab98b90ae655`.
  The immutable image digest and native identity configuration stay in private
  evidence. Subsequent operator-inventory and documentation changes are not
  claimed as redeployed serving code. Commit/CI evidence is recorded only
  after the exact workflow completes.
