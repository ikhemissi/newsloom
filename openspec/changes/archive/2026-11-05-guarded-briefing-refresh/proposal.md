# Proposal

## Why

The user explicitly requested a fresh briefing and TL;DR now to inspect the
deployed architect-focused policy. The delivered worker intentionally refuses
successful daily slots, and its failed-run retry cannot replace a published
artifact; deleting that slot or pretending it failed would destroy honest history.

## What Changes

- Add an explicitly invoked operator-only editorial revision of the current
  published daily window, guarded by its expected artifact version and a stable
  request ID. Ordinary scheduled execution and `retry-failed` keep their guards.
- Preserve the previous successful artifact and run metadata in a restricted
  append-only revision audit before generation. Keep the existing report visible
  until the replacement summary and derived TL;DR validate and publish atomically.
- Continue existing physical-call ordinals and retain every previous attempt,
  token/cost row and unknown-usage marker. Refuse concurrent, stale, duplicate or
  uncertain dispatch instead of replaying generation.
- Use the already deployed architect policy and the same fixed seven-day window;
  record a fresh consistent stored-news snapshot rather than silently moving
  today's cutoff to the invocation time.
- After local verification and owning migration/worker deployment, execute the
  user-authorized revision and verify that the published version changed and is
  readable through the existing protected interface.

## Capabilities

### New Capabilities

- `briefing-editorial-revisions`: Audited, explicit replacement of a published
  daily briefing without losing the previous publication or operation accounting.

### Modified Capabilities

None in main specs. Briefing behavior remains in the active
[daily](../../daily-news-briefing/proposal.md) and
[architect-focused](../../architect-focused-briefing/proposal.md) slices.
Implementation must reconcile their operational guidance with this separately
authorized exception, not weaken their ordinary once-only execution contract.

## Impact

A narrow [PRD-3](../../../../docs/prd-3.md) / [P3-C08](../../../../docs/prd-3-capabilities.md#p3-c08-shared-daily-weekly-news-briefing)
operation following the deployed architect refinement. Affects worker
CLI/repository execution, one additive migration, real-role and generation
tests, and owning runbooks/acceptance artifacts.

The current command surface, migration `006_briefing_retry.sql` and retry tests
explicitly reject a successful or already-published slot. Its failed-only audit
table cannot truthfully store a prior successful publication, so this needs a
separate revision record rather than a SQL reset or a retry flag.

No new cloud resource, model/version/capacity, region, browser permission,
dependency, personalized scope or monetary cap. Use existing identities and the
existing dated model-price basis; measure additional inference separately from
hosting/build costs. The migration grants only restricted revision-table access
to the existing writer. No unresolved model, regional-capacity or identity choice.

Out of scope: public regeneration endpoints/buttons, historical browsing,
automatic revisions, arbitrary cutoffs, article fetching, evaluation replay and
claiming a manual revision proves actual scheduling or user quality acceptance.
