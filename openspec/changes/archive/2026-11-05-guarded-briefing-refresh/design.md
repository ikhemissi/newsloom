# Design

## Context

See the [proposal](proposal.md) and
[requirements](specs/briefing-editorial-revisions/spec.md).

`newsloom_briefing.cli.execute()` supports normal daily claim and guarded
failed-run retry. Both use `Repository` and a session advisory lock.
`briefing_runs` is keyed by cutoff, `briefing_calls` by cutoff/ordinal, and
`briefing_current` holds one protected artifact. Retry preserves failed run
metadata in `briefing_attempts`, whose database constraint explicitly requires
`status='failed'`. The current publication is successful, not a failed retry.

The deployed architect worker can already generate the desired output. Its
compatible API/UI consumers are deployed. `inspect` parses the actual old
publication and reports content-free usage, but does not yet expose its version
for a version-bound operator action. The existing read projection returns the
latest attempt state and current artifact independently, so it can retain last
good content during another attempt. API cache lifetime is bounded to 60 seconds.

## Goals / Non-Goals

**Goals:** An explicit, repeatable and idempotent operator path; original
success/cost preservation; atomic replacement; immediate production generation
using the approved policy.

**Non-Goals:** A force/reset command, arbitrary historical windows, public write
API, broader credentials, user impersonation, automatic reruns or a history UI.

## Decisions

### 1. Separate operator mode, not a weakened daily guard

Add a typed `revise-published` CLI mode requiring UUID request ID, UUID expected
version and an allowlisted reason such as `editorial-policy-upgrade`. Inspect
the current version through a safe metadata-only operator read; do not export
the report or user/browser credentials to obtain it.

Reuse the current fixed daily cutoff, session lock and generation deadline.
Under a transaction, lock the slot/current artifact and check expected version,
current cutoff, attempt status and fully observed prior usage. Refuse when the
existing job's bounded lifetime could cross the next daily cutoff. Recheck
current cutoff and base version at publication.

Normal `run` and `retry-failed` retain their existing restrictions. A separate
mode makes the approved editorial exception explicit instead of overloading
failed retry, changing the cron, inventing a cutoff or resetting a ready row.

### 2. Additive append-only revision audit

Use the next versioned migration to create a writer-restricted
`briefing_revisions` audit table. Record request UUID, cutoff, requested-at,
allowlisted reason, expected/base version, prior last-call ordinal, prior run
metadata and prior artifact payload. Enforce request uniqueness and JSON/UUID/
state consistency. Preserve prior migration bytes and failed-only audit meaning.

Atomically insert this immutable record before moving the latest slot attempt
to running. Do not mark the original successful attempt failed: its original
ready metadata is retained verbatim. Archive payloads are protected operational
data, not telemetry; grant only SELECT/INSERT to the existing writer, no archive
access to MCP/readers, and no new cloud identity/RBAC scope.

Reusing `briefing_attempts.failed_run` would violate its check and mislabel
success. Replacing the complete cutoff-keyed accounting model is unnecessary
for this small operator operation.

### 3. Preserve the accounting and generation pipeline

Reuse the deployed snapshot, factual extraction, selection, summary, TL;DR and
validation code. Refactor only the claim/publish orchestration needed to share
it, not a second synthesis implementation. Register every new call through the
same durable intent/usage path, starting after the prior maximum ordinal.

The same request ID never generates again, even if the caller lost the job
start/response. Report an explicit existing-request outcome. Never manufacture
zero usage or reset original costs.

A failed revision with fully observed usage can be continued only through a
fresh explicit revision request, matching the still-published base and the
latest revision lineage, and an explicit known-validation-failure allowlist.
Running, pending, unknown or unrelated failures are refused. Keep ordinary
failed-run retry unchanged; do not build a generic automatic replay loop.

### 4. Keep last good content until compare-and-publish

Leave `briefing_current` untouched while generating. In one publication
transaction, verify the expected base is still current, publish a newly
validated artifact version containing both summary and TL;DR, and finish the
latest attempt as ready. On any failure, record its safe category/usage and
retain the old payload. The current attempt state describes the latest refresh;
the original successful run remains available in the immutable audit.

Keep the prior seven-day bounds. A fresh read-only snapshot may include late
committed rows eligible for that fixed window; record its new count/hash rather
than claiming byte-identical evidence or silently moving the cutoff to now.

Existing API cache/authorization and browser version handling suffice: a new
version is observable within the current 60-second bound and resets the native
collapsible. Do not introduce invalidation credentials, a browser regenerate
button or protected-token export to accelerate verification.

### 5. Migration-first owning rollout, then explicit dispatch

Build fresh migration and worker images from the exact scoped tree excluding
parked work. Review native azd previews and apply the additive migration through
the existing migration job before deploying the compatible worker. No API/UI
image update is needed unless tests identify a directly coupled contract defect;
preserve their actual deployed source associations.

Use the existing job-start override to invoke the typed worker command with one
persisted request ID and inspected expected version. The user's immediate refresh
request authorizes this dispatch after implementation, not repeated uncertain
attempts. Do not call ordinary daily `run` and present its duplicate skip as a
refresh.

Read back the resulting artifact version/policy, cutoff, generation time,
combined word count, citations, revision lineage and per-attempt/cumulative
usage without logging report content. Leave real user semantic review and
actual daily scheduling acceptance separate.

## Risks / Trade-offs

- Extra cost for explicit revision -> record incremental and cumulative physical
  usage at the retained dated price basis; no invented dollar ceiling.
- Failure or unsupported factual output -> preserve the current publication and
  fail visibly; no generic successful fallback or unknown-operation replay.
- Delayed caller/duplicate job -> stable request UUID, base-version checks and
  shared session lock prevent multiple dispatched attempts.
- Revision approaching the next daily slot -> refuse before dispatch using the
  existing full job-lifetime bound, then recheck the cutoff at publication.
- Audit stores prior generated report -> restrict it to the database writer and
  migration authority, never telemetry, MCP, browser history or committed files.

## Migration Plan

Reconcile the directly related PRD/runbook and active refinement guidance with
this new explicitly authorized operation; keep their historical evidence intact.
Test the additive migration and real-role guards, then deploy migration before
worker using retained dev state. Verify unchanged other workload/model/grant
fingerprints, execute the one requested revision and publish measured CI evidence.

Rollback restores the earlier worker image without dropping audit/history or
rewriting ledger rows. Preserve the last good publication and all incurred usage.
An actual failed/unknown execution is reconciled, not erased to make rollback
look successful.
