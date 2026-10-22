# Tasks

## 1. Repository foundation

- [x] 1.1 Extract PRDs, capabilities/user stories, ADRs, platform notes, and delivery guidance into standalone documentation without duplicate full specifications.
- [x] 1.2 Create the uv workspace, typed shared package, and three service package boundaries.
- [x] 1.3 Preserve and validate all 42 initial feeds and category allowlists.
- [x] 1.4 Configure Ruff, strict mypy, pytest, pre-commit, and the identifier guard.
- [x] 1.5 Initialize pinned OpenSpec with GitHub Copilot integration and acceptance scenarios.

## 2. Infrastructure and delivery tooling

- [x] 2.1 Configure azd/Terraform with an RBAC-only remote backend and local-test hooks.
- [x] 2.2 Add a one-off, destruction-protected state-bootstrap root and verification runbook.
- [x] 2.3 Configure CI to execute the same cloud-credential-free local checks.

## 3. Verification and acceptance

- [x] 3.1 Pass the complete local check script, workspace builds, and pre-commit configuration checks.
- [ ] 3.2 Select the Azure environment and apply the reviewed state-bootstrap plan.
- [ ] 3.3 Verify state blob read/write/delete/lease through RBAC and shared-key disablement in Azure.
- [ ] 3.4 Verify the checks pass in GitHub Actions and record the run evidence.
- [ ] 3.5 Commit only after required local and Azure checks; archive only after all acceptance gates pass.

## Local evidence

Verified on 2026-10-22 with Python 3.15.1, uv 0.13.5, OpenSpec 1.14.3,
Terraform 1.15.8, and AzureRM 5.10.0:

- `bash scripts/check.sh`: passed Ruff lint/format, strict mypy, 29 pytest cases,
  42-feed validation, identifier guard, strict OpenSpec validation, Terraform
  formatting/validation for both roots, and 3 mocked-provider Terraform tests.
- `uv build --all-packages`: built wheels and source distributions for all four packages.
- `npm ci --no-audit --no-fund`: reproduced the pinned OpenSpec installation.
- `uv run pre-commit validate-config`: passed; local pre-commit hook installed.
- `bash -n scripts/check.sh`: passed.
- Before removal of the duplicate source documents, all 11 extracted ADRs and all
  42 configured feed objects/allowlists were verified to match the planning input.
  Phase PRDs and capability documents retain the product requirements; platform
  notes retain the remaining resource checklist, capacity caveat, and feed-size example.
- `azd env list --output json`: parsed the project and returned no environments.

No Azure plan/apply, live RBAC probe, GitHub Actions run, deployment, commit, or
archival was performed. Tasks 3.2-3.5 remain operator acceptance gates.
