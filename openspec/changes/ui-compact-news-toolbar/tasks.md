# Tasks

## 1. Compact toolbar

- [x] 1.1 Remove the visible hero and move Refresh/Clear search into the filter form as non-submit actions; preserve hidden heading/focus and concise search context. Verify component regressions for applied versus draft filters, clearing search and unchanged requests.
- [x] 1.2 Add browser layout assertions for recovered hero space, desktop toolbar alignment, mobile wrapping and accessible navigation; verify the authored browser/axe suite passes.
- [x] 1.3 Update the owning UI runbook with the compact toolbar and honest local/deployed status; verify its local links.

## 2. Integration and publication

- [x] 2.1 Run the existing local UI checks, primary repository gate and strict OpenSpec validation; selectively commit the slice with recorded results, preserving unrelated work and existing open acceptance.
- [x] 2.2 Prepare a fresh immutable UI image and owning azd/Terraform preview, obtain approval, deploy only the UI app and verify actual anonymous Azure layout/assets/configuration and preserved backends; record measured evidence and passing publication CI, retaining the approved signed-in acceptance boundary in task 2.3.
- [ ] 2.3 Verify the actual signed-in Azure toolbar alignment, Refresh/Clear search semantics and desktop/mobile accessibility through the permitted regular-browser journey; record measured evidence without another test-browser sign-in or exported authentication state.

## Local verification

- Focused App/filter/navigation command: 23 tests passed; workspace lint and
  typecheck passed.
- `NEWSLOOM_BROWSER_ENGINE=podman bash scripts/check-ui-browser.sh`: nine authored
  browser journeys passed, including desktop alignment, absent hero geometry,
  mobile custom-date wrapping, detail navigation and axe checks.
- Strict current-change and repository OpenSpec validation passed (22 items);
  13 owning-runbook/planning local Markdown links and anchors checked.
- `NEWSLOOM_BROWSER_ENGINE=podman bash scripts/check.sh` passed against the
  working tree, including 503 evaluator tests, 1,656 application tests
  (69 conditional skips), 52 frontend tests, nine browser journeys, runtime,
  lint/type, build, OpenSpec and backend-disabled Terraform gates. Parked
  evaluation work was neither staged nor included in this slice.

## Deployment evidence

- Implementation `1c44c0a` passed exact-source CI `41493885878`; the image's
  source hash exactly matches the committed eligible build inputs:
  `1842f4750ffc15f43bc802017e6167d1f6b23148d3d17dea339787418052b684`.
- The fresh native preview changed only the existing UI image and
  UI_RUNTIME_REVISION: one update, zero creates/deletes. The user explicitly
  approved this plan and early-access publication with signed-in checks open;
  that approval was consumed once, not reused from an earlier slice.
- Native `azd provision ui` and its preprovision gate passed. Owning readback
  verified the ready revision, exact image/configuration, existing identity/
  registry grant/consent and API prerequisites. Production nonroot smoke passed.
- All three served script/CSS assets matched the pinned production filenames
  and bytes; public config/CSP/cache headers and direct detail SPA fallback
  passed. UI health and API readiness returned 200; anonymous API access
  remained 401. Six non-UI app/job fingerprints and 52 parked paths were
  unchanged. No verification inference was dispatched.
- Anonymous real-Azure browser checks at 1440px and 390px confirmed no hero
  gap/overflow, zero axe violations and no protected requests or script errors.
  Authored tests prove signed-in layout locally; they are not signed-in Azure
  proof. The user-approved open acceptance is tracked separately in task 2.3.

## Workflow follow-up

- Do not archive this or earlier UI/API changes while acceptance remains open.
