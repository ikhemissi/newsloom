# Tasks

## 0. Briefing history

- [ ] 0.1 Add migration `008_briefing_history.sql` (append-only table keyed by version, writer INSERT/SELECT, MCP SELECT, backfill from current and revision audits) and append on every publish in the same transaction; verify with real-role tests (no UPDATE/DELETE, failure adds nothing, backfill has no duplicates).

## 1. Storage and API

- [ ] 1.1 Add migration `009_feedback.sql` (table, constraints, INSERT/SELECT grants to `newsloom_mcp`); verify with real-role database tests that the role cannot UPDATE or DELETE.
- [ ] 1.2 Add `POST /api/v1/feedback` with `feedback.write` scope, validation (rating, 1,000-char comment, known briefing version, bounded research snapshot) and reader hashing; verify with API tests including 403 `insufficient_scope` and no content in logs.
- [ ] 1.3 Add reviewer `GET /api/v1/feedback` and `/export` (JSONL, latest vote per reader and item, filters) gated by `Feedback.Reviewer`; verify 403 without the role and export shape.

## 2. Identity

- [ ] 2.1 Add the `feedback.write` delegated scope and `Feedback.Reviewer` app role to the MCP API registration and the UI permission/consent in the identity layers; verify with Terraform tests and owning readback.

## 3. UI

- [ ] 3.1 Add thumbs up/down and optional comment to the briefing and each completed research answer, showing the current vote; verify with component tests and browser journeys including keyboard and axe.
- [ ] 3.2 Add the reviewer page with filters and JSONL export, visible only with the role; verify with component tests.

## 4. Eval loop and delivery

- [ ] 4.1 Add `scripts/feedback-to-evals.py` and include `.cache/eval-cases/` in `scripts/eval.sh`; verify with a synthetic export fixture test.
- [ ] 4.2 Deploy migration, MCP app, identity and UI through azd (draft PR, then ready PR with full checks and evals); verify readbacks, anonymous 401, and record a real thumbs-down from the user's browser as acceptance.
