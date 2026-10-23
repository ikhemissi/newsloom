# Design

## Context

See [the proposal](proposal.md) for the approved combined slice and
[the ingestion](specs/feed-ingestion/spec.md) /
[screening](specs/content-screening/spec.md) contracts for behavior.

Observed implementation: the ingestion package is currently a boundary; core
already validates the 42-source catalogue. The platform package has real async
Entra database connections, checksum-ledger migrations, bounded ACR builds/job
execution, and safe logging. azd currently ends at the migrations layer. The image
context excludes `config`, and its source hash does not cover that catalogue yet.
There are no domain tables or ingestion runtime grants.

## Goals / Non-Goals

**Goals:** one deployable job, three ordinary database tables, real screening,
and direct proof of fetch-to-database behavior.

**Non-Goals:** a generic pipeline framework, additional messaging/storage services,
runtime DDL, a scanner service, or advance implementation of enrichment.

## Decisions

### 1. Keep ingestion in the existing package

Use small typed modules for retrieval/parsing, scanner, repository, and job entry
point. Reuse the core catalogue types and existing operator/migration patterns;
extract only helpers actually shared. Do not make ingestion depend on all platform
probe inputs or create a configuration/plugin framework.

Use async HTTP with manual redirects and a resolver/transport that connects only
to addresses validated for that request. Verify TLS against the hostname. Apply
the same policy to robots requests. Missing robots policy is distinct from denied
or temporarily unreadable policy. No publisher-controlled article link is fetched.
Use safe XML parsing with DTD/entity rejection and bounded plain-text extraction;
add only the dependencies needed for those functions.

### 2. Use the approved explicit operating profile

| Setting | Initial development value |
| --- | --- |
| Schedule | `*/30 * * * *`, UTC |
| Concurrent feed retrievals | 4 |
| Feed body | 8 MiB, bounded during streaming and decompression |
| Robots body | 256 KiB |
| Connect / request timeout | 5 / 30 seconds |
| Total per-feed retrieval/parse budget | 60 seconds, including redirects/retries |
| Job deadline | 900 seconds, including screening and shutdown |
| Redirects | 3 |
| Retries | 2, bounded backoff; defer excessive Retry-After |
| Entries per feed document | 1,000 |
| Normalized entry text | 32 KiB of UTF-8, truncated at a character boundary |

Byte, entry, redirect, and elapsed limits need tests exactly at and beyond their
boundaries. Exceeding the entry limit fails that document rather than saving its
validator after silently ignoring later entries. The text bound is intentional
normalization, not permission to truncate the XML body and call it successful.
Reject invalid configuration before running. Scanner throughput has its own
deployment rate limit; do not interpret four HTTP fetches as four unrestricted
model callers.

### 3. Persist only the state this slice needs

Add the next versioned migration through the retained migration job. Never edit
the already-applied migration checksums or create schema at application startup.

| Table | Minimal responsibility |
| --- | --- |
| `feed_sources` | Catalogue ID/configuration mirror, ETag, fetch times/outcome, safe per-run counts/correlation. The file remains authoritative; removed sources are not fetched or used to delete stored entries. |
| `ingestion_queue` | Normalized accepted entry, source/GUID/canonical URL, ingestion correlation, screening metadata, pending status and creation time. |
| `quarantine` | Normalized unaccepted entry, identity, rejection or retryable disposition, bounded score/model/threshold or safe failure code, timestamps and retry bookkeeping. |

Quarantine distinguishes an actual rejection from deferred screening; an error
never masquerades as a model verdict. Rejected records are retained, not
automatically retried/deleted. Deferred records can be retried even if the source
later returns 304, and move atomically to the accepted queue on acceptance.
Resolve their retry state and retain a reference to the accepted row rather than
granting ingestion permission to delete quarantine history.
This reuses the same three tables instead of adding a staging service/table.

Enforce source/GUID and canonical-URL uniqueness for entries with those values,
including checks across queue/quarantine. Serialize overlapping ingestion runs
with a database advisory lock and keep persistence transactions short and
serialized inside the job. This is sufficient for the current single ingestion
writer; do not build distributed workers or enrichment leases prematurely.
Crash/replay tests must demonstrate that the lock releases and no duplicate
disposition or validator-induced loss occurs.

Commit source validators only after eligible entries are durably accounted for,
and never replace them after parsing zero entries. Retry deferred entries
independently of HTTP validators. Preserve URL query and fragment semantics during
conservative canonicalization. Feed entries may identify separate releases with
anchors on the same page; retain those fragments in the stored entry URL and its
deduplication key. Source/GUID deduplication remains unchanged. Do not invent
publisher-specific URL rules. This corrects the original fragment-stripping plan,
as explicitly approved after the two-source live test exposed lost Atom releases.
Normalize dates from published, then updated time; if both are absent, record
retrieval time explicitly as the fallback rather than pretending it was published.

Grant the ingestion role only required read/insert/update permissions on these
tables and required sequences; no runtime DDL/admin or quarantine DELETE.
Enrichment/MCP table grants wait for their slices.

### 4. Use the deployed Decision model, not a bypass

Implement one typed scanner protocol and one real runtime adapter using managed
identity and the already-verified `providers/microsoft/v1/systemone` route and
`answers.<question>.noul` shape. Send synthetic labelled cases for calibration
and normalized publisher content only as untrusted state. A fake scanner belongs
only in tests.

Select the threshold from calibration examples, then test a separate labelled
clean/hostile set with fixed expected outcomes. Record the threshold, model
version, sample counts, and observed mistakes; do not choose a numeric default
or weaken expectations just to enable the schedule. Missing calibration remains
an explicit blocker to live admission.

Reuse the existing ingestion identity for bounded calibration executions in Azure.
Keep the real job's schedule disabled during calibration/first verification.
Count model retries toward its configured 60-request/minute limit, bound waits by
the overall deadline, and persist outstanding work as deferred. A large catalogue
may need later runs to finish screening; report pending deferred work honestly.
No source entry may be discarded merely to finish within 900 seconds.

### 5. Reuse native azd build, migration, and execution plumbing

Add one ingestion Terraform layer after migrations and one real job in the
existing environment with the existing ingestion identity. Follow the retained
job's variable-driven tags, managed-identity pull, and immutable digest pattern.
Reuse the bounded platform operator helpers with only the small image/job
parameters needed; no direct Terraform apply or second deployment tool.

Include the feed catalogue in the ingestion image and its source hash. Update the
allowlisted build context rather than accidentally sending ignored deployment
state or credentials. Keep all existing shared resources/state intact.
Provision with scheduling disabled, calibrate, run manual acceptance, then enable
the approved schedule through azd and confirm convergence. A failed acceptance
does not authorize deleting/recreating the platform.
AzureRM 5.10 marks manual/scheduled trigger changes as replacement. After reviewing
the actual preview, the user explicitly approved recreating only the ingestion job
to enable scheduling, preserving its name, shared resources, and all database rows.
Do not introduce another provider merely to avoid this approved job-only operation;
retain evidence outside the job because its execution history may reset.

### 6. Prove behavior immediately at the appropriate scale

Local unit tests use deterministic RSS/Atom, hostile-network/XML, category,
conditional-request, model-response, and large synthetic full-text fixtures.
Database tests reuse disposable PostgreSQL 18/pgvector and cover actual SQL,
replay, disposition transitions, uniqueness, rollback, and role restrictions.
These tests do not call publishers or models in CI.

The local live smoke test selects exactly one RSS and one Atom source, initially
`microsoft-foundry-devblog` and `vertex-ai-release-notes`. Retrieve/parse those
two and exercise their repository writes against the disposable database;
live model decisions are verified under managed identity in Azure, not by adding
developer database grants or calling all feeds locally.

After azd deployment, start the real ingestion job immediately using the existing
bounded execution path, without waiting for cron. Its normal Azure run uses the
whole catalogue. Read back fixed, read-only aggregate queries through the
retained migration job/identity: source outcomes, queue/quarantine counts,
accepted screening provenance, duplicate groups, and retryable counts. This is a
separate database read, not a replay of the ingestion process's in-memory counters.

Require actual fetched entries and nonzero model-accepted pending rows. Report
each unavailable/filtered/not-modified source distinctly; do not fake universal
publisher availability. Run again immediately with `--force`; compare unchanged
entry identities and duplicate queries, allowing genuinely new publisher entries.
Confirm safe run telemetry and absence of content/credential canaries.

## Risks / Trade-offs

- **Publisher outages or robots restrictions** -> report the source outcome and
  distinguish external availability from a code failure; never bypass policy.
- **Scanner rate limit and retirement** -> bounded resumable screening using the
  current deployment; refresh availability and preserve ADR-6's replacement risk.
- **Schema/probe evolution** -> platform checks must now recognize the owning
  slice's tables/grants rather than keep asserting zero domain tables forever.
  Preserve initialization and access guarantees instead of deleting those checks.
- **Uncalibrated decisions** -> keep live admission/scheduling blocked, retain safe
  evidence, and surface the failed fixture behavior instead of accepting blindly.

## Migration Plan

Implement and test each coherent increment locally. Apply additive migrations
through the existing azd layer, build/provision the real ingestion job, calibrate,
then perform the immediate full-catalogue Azure run and database read-back.
Enable scheduling only after those checks; repeat previews to confirm no shared
resource replacement and retain source/entry state.

Commit only verified work, push, and verify exact-commit CI before marking
acceptance complete. Fix forward on failure; review trigger-change replacements
before applying them, and never drop tables, quarantine, or shared services to pause
ingestion.
