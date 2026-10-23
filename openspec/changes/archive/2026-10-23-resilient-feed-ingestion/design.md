# Design

## Context

See [the proposal](proposal.md) for motivation and scope. These are planned
changes, not a claim that the observed defects have already been fixed.

The current parser builds every `Entry` before returning; one item error prevents
the job from staging any siblings. `plain()` feeds `HTMLParser` without closing
it, which can leave an ordinary ampersand-containing final chunk buffered.
`PublicClient.request()` already disables redirects and pins public DNS answers;
the higher-level feed fetcher follows bounded redirects and must not be reused
unchanged for article navigation.

The existing `feed_sources.counts` JSONB field holds latest-run retrieval counts.
`finish_source()` replaces that object before screening, while `decide()` already
commits queue/quarantine transitions atomically. No new table is needed.
The existing `Entry` contract permits empty text, and URL queries/fragments
already participate in identity.

## Goals / Non-Goals

**Goals:** keep changes inside the existing parser, client, orchestration,
repository and diagnostics; make each outcome observable without content logs;
reuse the same recovery behavior in the job and two-source local smoke command.

**Non-Goals:** a crawler, publisher-specific extraction plugins, draft-item storage,
an LLM call inside ingestion, lifetime analytics, new resources or runtime DDL.
The [requirements](specs/feed-ingestion/spec.md) own externally visible behavior.

## Decisions

### 1. Separate document safety from item normalization

Retain whole-document byte, XML/DTD/entity and item-count checks before processing
individual nodes. Return typed per-item normalization outcomes instead of letting
expected item validation errors abort the document. Flush `PlainText` at EOF for
both title and body before deciding a field is missing.

Parse enough identity and category information to filter and recognize existing
durable identities before doing article recovery. Reuse the repository's current
cross-disposition identity predicate rather than introducing different dedup rules.
Keep the final staging check as well. Unexpected implementation or persistence
errors remain explicit failures, not malformed-item fallbacks.

Alternative rejected: catching every exception around a whole feed, or treating
each failure as a security verdict. Both conceal the actual failure boundary.

### 2. Fill missing fields from one protected response

For an eligible new item with missing title or text:

1. Preserve each usable normalized feed field.
2. If needed, authorize the article URL using the existing HTTPS/public-DNS and
   robots protections, then make one direct GET with redirects disabled.
3. Read inline JSON-LD article headline/description/articleBody and OpenGraph
   title/description as available. Accept only correctly typed, readable fields
   associated with the article, not unrelated organization or navigation metadata.
4. If still incomplete, use a visible article heading and bounded text from an
   article/main content region of that same HTML, excluding scripts/styles and
   navigation boilerplate. Use the existing HTML/plain-text machinery rather than
   a browser, generic crawling framework or remote JSON-LD resolver.
5. Validate the resulting entry and stage it for the unchanged scanner.

Do not replace valid feed fields, follow canonical links, rewrite the entry URL
from metadata, or make another GET for body extraction. A metadata headline plus
HTML body is the article-body path. The original recovered publisher text, not a
generated summary, is scanned and stored for later enrichment.

Keep the current 8 MiB streamed/decompressed response bound, 256 KiB robots bound,
5/30-second connection/request limits, four feed slots, 60-second per-feed budget,
900-second job budget and 32 KiB normalized-text limit. Article requests consume
those budgets; no per-item fresh feed deadline, extra concurrency or immediate
article retry is added. Existing feed redirect/retry behavior stays unchanged.

Missing text alone does not create a new schema rejection: attempt recovery, but
retain an otherwise valid title-only entry if recovery supplies nothing. Emit a
safe recovery failure when appropriate. A genuinely missing required title or
invalid identity that cannot be recovered is a malformed drop.

Alternative rejected: always downloading articles, or adding GPT summarization
as a fallback. The former adds unnecessary traffic; the latter changes inference
permissions and advances enrichment without need.

### 3. Distinguish permanent item failure from retryable recovery

Count unusable items after applicable recovery as `malformed_rejected`; do not
store invalid `Entry` JSON as ordinary deferred screening work. Security rejection
continues to mean an actual Decision verdict only.

A temporary HTTP failure, request timeout or exhausted budget that prevents an
otherwise necessary recovery increments `recovery_deferred`, not malformed or
security rejection. Keep prior source validators so the next run can obtain the
body again; valid siblings already staged remain durable and deduplicate on replay.
An ordinary policy refusal or permanently unusable response is an explicit
recovery failure; drop only an item that still cannot satisfy normalization.

Commit new validators only after durable items and malformed counters have been
accounted for, never after an all-malformed/empty document or incomplete retryable
recovery. Already-durable identities can satisfy accounting without another fetch.
This uses existing conditional-request state instead of a new draft queue.

### 4. Extend the existing latest-run counters

Keep existing retrieval keys and add documented integer counters:

| Counter group | Meaning |
| --- | --- |
| `accepted`, `security_rejected`, `deferred` | Screening outcomes actually committed during this run for this source; deferred counts decisions, not current backlog depth. |
| `malformed_rejected` | Items discarded for parsing/normalization failure, separate from filtering and model rejection. |
| `feed_item`, `article_metadata`, `article_body` | Successfully staged new items, classified once by the deepest tier that supplied fields. |
| `recovery_attempted`, `recovery_failed`, `recovery_deferred` | Recovery attempts including authorization, unsuccessful outcomes and unfinished necessary recovery; not acceptance counts. |

`last_run` ties these values to one correlation. Initialize retrieval and screening
keys for each selected source, including 304 and fetch-failure outcomes. Increment
decision counters inside the same transaction as `decide()`, for that source and
current run. Do not later overwrite them with retrieval-only totals. Reject a
missing/mismatched counter row explicitly so its decision transaction rolls back.

Previously deferred work can be accepted after a 304 or failed feed fetch; those
decision counts need not equal this run's `staged` or acquisition counts.
Duplicates, filtered entries and malformed drops do not increment acquisition
paths. Replaying a rejected identity does not produce another security rejection.
Unselected source rows are unchanged. A new run replaces the previous run's
counters; these are deliberately not lifetime totals or a history table.

Extend existing allowlisted diagnostics and read-only database readback with
source IDs, run correlation and these counters. Never include recovered content,
raw article URLs, publisher GUIDs, model inputs or outputs.

### 5. Retire only the broken catalogue entry

Remove Solo.io without modifying or duplicating agentgateway. Update the offline
catalogue assertions and current source-count documentation to 41. Historical
`feed_sources`, queue and quarantine rows remain: database row count is not an
active-catalogue count. Do not change any applied migration or issue deletes.

## Risks / Trade-offs

- More article traffic can exhaust existing deadlines: recover only missing
  fields for new eligible work, share deadlines and report retryable work honestly.
- HTML can omit usable metadata/content: report item failure rather than adding
  JavaScript execution, redirects or invented summaries.
- Latest-run counts can be mistaken for totals: expose their correlation and
  distinguish acquisition from decisions over existing backlog.
- Retaining validators can repeat a problematic body: siblings deduplicate, while
  recovery can retry without a new table; content not yet normalizable is not a
  claim of durably staged screening work.
- The current scanner can flag legitimate security material: keep the original
  eight rejections and all screening settings unchanged for manual review.
- OpenAI remains over the document cap: report that known failure explicitly;
  this change does not silently raise the limit.

## Migration Plan

1. Publish the already-verified ingestion baseline specs through the normal sync
   workflow before reconciling this delta into main specs. Do not implicitly
   archive the completed change or rewrite its evidence.
2. Implement and run focused offline/database regressions and the repository
   gate. Live local testing stays limited to one RSS and one Atom source.
3. Reuse the persistent azd environment; preview and deploy the rebuilt immutable
   image without changing identities, model permissions, shared resources or the
   enabled schedule. The counts JSON extension needs no schema migration.
4. Start ingestion immediately in Azure, inspect actual source/path outcomes and
   read database aggregates independently. Force an immediate repeat to verify
   deduplication. Compare the original eight rejected rows read-only; record only
   safe aggregate preservation evidence in the repository.
5. Commit only after local and Azure verification, then record exact-commit CI.
   Leave unverified acceptance tasks unchecked.

If rollout fails, restore the previously verified image through the existing azd
workflow without resetting state or database rows. The old runtime can ignore
additional JSON keys. An intentional code/catalogue rollback must not be disguised
as successful acceptance of this follow-up.
