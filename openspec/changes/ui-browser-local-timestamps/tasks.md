# Tasks

## 1. Timestamp presentation

- [x] 1.1 Share browser-locale date/time formatting with an explicit instant-specific UTC offset across cards, detail and read metadata; verify controlled Paris/New York midnight, DST and fractional-offset tests plus preserved raw datetime values and DTO failure behavior.
- [x] 1.2 Add textual future-date indications and one shared minute/resumption clock with timer/listener cleanup; verify future/equal/past and equivalent-offset comparisons, clock/zone changes, sign-out/unmount and zero additional catalogue/search/paging/research requests or cache-age mutation.
- [x] 1.3 Add authored browser journeys with explicit timezones/clocks and update the owning UI runbook; verify card/detail/metadata consistency, marker expiry, compact desktop/mobile layout, axe and local documentation links.

## 2. Integration and rollout

- [ ] 2.1 Run focused tests, existing workspace lint/types/build, the primary repository gate and strict OpenSpec validation; selectively commit/publish this slice and record passing exact-source CI without disturbing parked work.
- [ ] 2.2 Build a fresh immutable UI image, review/approve its owning azd preview and deploy only the existing UI app; verify ready revision/configuration/identity, pinned asset parity, unchanged backends/jobs and actual available Azure behavior, then commit measured rollout/CI evidence.
- [ ] 2.3 Verify real signed-in Azure timestamp/offset/future-label behavior and accessibility in the permitted regular-browser journey and record measured evidence. Keep this task unchecked if unavailable; early-access publication requires fresh explicit approval without another browser sign-in or credential export.

## Local verification

- All 61 frontend tests passed; the final focused timestamp/DTO command passed
  14 tests. Workspace lint and typecheck passed after the test-only corrections.
- The final pinned browser runner passed 13 authored journeys, including Paris,
  New York and Kathmandu midnight/offset display, future-label expiry and real
  runtime zone changes with a frozen clock. Existing compact/mobile/axe,
  navigation, filters, pagination and research journeys remain passing.
- Nonroot production container smoke and strict current-change validation
  passed; 14 owning-runbook/planning local Markdown links and anchors checked.
- `NEWSLOOM_BROWSER_ENGINE=podman bash scripts/check.sh` passed against the
  working tree: 503 evaluator tests, 1,656 application tests (69 conditional
  skips), 61 frontend tests, 13 authored browser journeys, runtime imports,
  lint/types/build, 23 strict OpenSpec items and Terraform gates. Parked
  evaluation work is not part of this slice's publication.
- No new Azure deployment or signed-in acceptance is claimed by these checks.

## Workflow follow-up

- Do not archive while this or earlier acceptance remains unverified.
