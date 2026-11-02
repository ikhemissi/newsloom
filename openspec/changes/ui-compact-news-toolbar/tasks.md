# Tasks

## 1. Compact toolbar

- [x] 1.1 Remove the visible hero and move Refresh/Clear search into the filter form as non-submit actions; preserve hidden heading/focus and concise search context. Verify component regressions for applied versus draft filters, clearing search and unchanged requests.
- [x] 1.2 Add browser layout assertions for recovered hero space, desktop toolbar alignment, mobile wrapping and accessible navigation; verify the authored browser/axe suite passes.
- [x] 1.3 Update the owning UI runbook with the compact toolbar and honest local/deployed status; verify its local links.

## 2. Integration and publication

- [x] 2.1 Run the existing local UI checks, primary repository gate and strict OpenSpec validation; selectively commit the slice with recorded results, preserving unrelated work and existing open acceptance.
- [ ] 2.2 Prepare a fresh immutable UI image and owning azd/Terraform preview, obtain approval, deploy only the UI app and verify actual Azure layout/assets/configuration and preserved backends; record measured evidence and passing publication CI. Leave unavailable signed-in acceptance explicitly open rather than inventing evidence or reusing an older exception.

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
- No Azure deployment or new signed-in acceptance is claimed.

## Workflow follow-up

- Do not archive this or earlier UI/API changes while acceptance remains open.
