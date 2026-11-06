# Tasks

## 0. Briefing history

- [x] 0.1 Add migration `008_briefing_history.sql` (append-only table keyed by version, writer INSERT/SELECT, MCP SELECT, backfill from current and revision audits) and append on every publish in the same transaction; verify with real-role tests (no UPDATE/DELETE, failure adds nothing, backfill has no duplicates).

## 1. Storage and API

- [x] 1.1 Add migration `009_feedback.sql` (table, constraints, INSERT/SELECT grants to `newsloom_mcp`); verify with real-role database tests that the role cannot UPDATE or DELETE.
- [x] 1.2 Add `POST /api/v1/feedback` with the `news.read` scope, validation (rating, 1,000-char comment, known briefing version, bounded research snapshot) and reader hashing; verify with API tests including 403 `insufficient_scope` and no content in logs.
- [x] 1.3 Add reviewer `GET /api/v1/feedback` and `/export` (JSONL, latest vote per reader and item, filters) gated by the reviewer allowlist; verify 403 when not listed and export shape.

## 2. Identity

- [x] 2.1 Wire `FEEDBACK_REVIEWER_OBJECT_IDS` through azd, the MCP Terraform layer and its deployment readback (no Entra changes); verify with Terraform tests and readback tests.

## 3. UI

- [x] 3.1 Add thumbs up/down and optional comment to the briefing and each completed research answer, showing the current vote; verify with component tests and browser journeys including keyboard and axe.
- [x] 3.2 Add the reviewer page with filters and JSONL export, visible only with the role; verify with component tests.

## 4. Eval loop and delivery

- [x] 4.1 Add `scripts/feedback-to-evals.py` and include `.cache/eval-cases/` in `scripts/eval.sh`; verify with a synthetic export fixture test.
- [ ] 4.2 Deploy migration, MCP app, identity and UI through azd (draft PR, then ready PR with full checks and evals); verify readbacks, anonymous 401, and record a real thumbs-down from the user's browser as acceptance.
