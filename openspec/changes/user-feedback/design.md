# Design

## Context

See [proposal](proposal.md) and [requirements](specs/user-feedback/spec.md).
The browser calls the MCP app's HTTP API under `/api/v1` with the delegated
`news.read` scope; the MCP app's database role is read-only. Research answers are
streamed over A2A and live only in the browser, identified by a task ID. Briefing
artifacts are stored with a version.

## Goals / Non-Goals

**Goals:** One-click rating with optional comment, minimal new authority, enough
context to reproduce a case, reviewer export.

**Non-Goals:** Public or anonymous feedback, agent-side persistence of answers,
automatic Foundry upload, analytics dashboards.

## Decisions

### 1. API in the existing MCP app, new scope

Add `POST /api/v1/feedback`, `GET /api/v1/feedback` and
`GET /api/v1/feedback/export` to the existing HTTP API. A new delegated scope
`feedback.write` on the MCP API app registration authorizes POST; the
`Feedback.Reviewer` app role authorizes GET. The UI app requests `feedback.write`
with admin consent through the existing identity layers.
Alternative rejected: a new feedback service (extra app, identity and cold start).

### 2. Storage

Migration `008_feedback.sql` creates `public.feedback` (UUID id, created_at,
reader_hash, target_type `briefing|research`, target_ref, rating, comment, snapshot
JSONB, snapshot_source `client`). Grant `newsloom_mcp` INSERT only, plus SELECT for
reviewer reads (the role check is in the API). Append-only: "latest wins" is
resolved at read time by `(reader_hash, target_type, target_ref)` and `created_at`,
so no UPDATE or DELETE grant is needed.

### 3. Pseudonymity

`reader_hash = sha256("newsloom-feedback:v1:" + tenant_id + ":" + oid)`. No secret
is needed (repository rule: no secrets), but the hash is reversible by anyone who
already knows a tenant object ID; this is documented as pseudonymous, not anonymous.

### 4. Research snapshot

The browser posts the question, answer claims/limitations/coverage, citations,
filters and task ID it already holds, validated against the existing answer schema
and size limits (MAX_ANSWER_BYTES). Provenance is marked client-supplied: the server
cannot prove the agent produced it. Good enough for triage; agent-side signing is a
possible later hardening.

### 5. UI

Thumbs up/down buttons under the TL;DR and under each completed answer; a small
optional comment field after a thumbs-down (also available after thumbs-up). Shows
the reader's current vote. Reviewer page `/feedback` visible only with the app role,
with filters and "Export JSONL".

### 6. Eval loop

`scripts/feedback-to-evals.py` reads an exported JSONL plus reviewer annotations
(`expected` per line) and writes cases to `.cache/eval-cases/`. `scripts/eval.sh`
includes them when present: briefing cases re-check the referenced artifact's
issue with the live eval; research cases are kept for the agent baseline. Real
content never enters git.

## Risks / Trade-offs

- Comments may contain personal data → length-bounded, never logged, reviewer-only
  access; retention policy (default 180 days) applied by a scheduled delete through
  the migration principal later if needed.
- Client-supplied snapshots could be fabricated → marked as such; triage only.
- New scope needs admin consent → applied via the existing identity layer and
  verified by readback before the UI uses it.

## Migration Plan

Migration first, then the MCP app (accepts the new scope), then identity/consent,
then the UI. Rollback hides the UI buttons; the table and scope can stay unused.
