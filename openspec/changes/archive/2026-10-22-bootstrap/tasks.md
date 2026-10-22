# Tasks

## 1. Repository foundation

- [x] 1.1 Extract PRDs, capabilities/user stories, ADRs, platform notes, and delivery guidance into standalone documentation without duplicate full specifications.
- [x] 1.2 Create the uv workspace, typed shared package, and three service package boundaries.
- [x] 1.3 Preserve and validate all 42 initial feeds and category allowlists.
- [x] 1.4 Configure Ruff, strict mypy, pytest, pre-commit, and the identifier guard.
- [x] 1.5 Initialize pinned OpenSpec with GitHub Copilot integration and acceptance scenarios.

## 2. Infrastructure and delivery tooling

- [x] 2.1 Configure azd/Terraform with an RBAC-only remote backend and local-test hooks.
- [x] 2.2 Add native azd layers for the destruction-protected state-bootstrap and application roots, with a state-preserving verification runbook.
- [x] 2.3 Configure CI to execute the same cloud-credential-free local checks.

## 3. Verification and acceptance

- [x] 3.1 Pass the complete local check script, workspace builds, and pre-commit configuration checks.
- [x] 3.2 Adopt existing bootstrap state into the persistent azd environment, review its azd preview, and provision through azd.
- [x] 3.3 Verify state blob read/write/delete/lease through RBAC and shared-key disablement in Azure.
- [x] 3.4 Verify the checks pass in GitHub Actions and record the run evidence.
- [x] 3.5 Commit only after required local and Azure checks; archive only after all acceptance gates pass.

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

The complete local check script passed again after the azd-layer migration.
After removing tests of azd's template substitution, the Python suite contains
29 tests; the three mocked state-safeguard tests remain.
Tenant-specific governance tests and mandatory tag-key validations were removed:
the two policy-control tags are deployment settings for the current tenant, not
project requirements.

## GitHub Actions evidence

- [Local checks run 39818194063](https://github.com/ikhemissi/newsloom/actions/runs/39818194063)
  passed on 2026-10-22 for the initial documentation commit `851680f`.
- [Local checks run 39825153185](https://github.com/ikhemissi/newsloom/actions/runs/39825153185)
  passed on 2026-10-22 for the verified azd bootstrap commit `288b85b`.
- The `checks` job passed dependency installation and `bash scripts/check.sh`
  without Azure credentials.

The initial scaffold and documentation were committed at the user's explicit
request before Azure acceptance. No application services have been deployed.

## Azure evidence

- Selected the persistent `dev` environment in France Central after resource-type,
  PostgreSQL 18/SKU, model availability/capacity, and subscription quota preflight.
  Actual database and model provisioning remains part of platform-skeleton.
- Initial creation used a reviewed direct-Terraform plan: four creates, no updates
  or deletes. This preceded the user's explicit azd-only correction. The created
  resources were a resource group, StorageV2 account, private container, and
  account-scoped `Storage Blob Data Contributor` assignment.
- Verified both taggable resources have `SecurityControl=Ignore` and
  `CostControl=Ignore`, supplied through the local `tags` variable map.
- Verified shared keys and anonymous blobs are disabled, HTTPS-only access and
  TLS 1.2 are configured, and an Entra-authenticated blob listing succeeds.
- Passed an Entra-only probe: uploaded a disposable blob, downloaded and compared
  its bytes, acquired and released a lease, deleted it, and verified it no longer
  exists. Cleaned up the local probe files.
- Saved the RBAC backend and governance tag inputs in the ignored azd environment.
- Re-ran the local checks after Azure verification; all passed. A refreshed
  Terraform plan reported no changes to the deployed state infrastructure.

### Native azd verification

- Adopted the existing bootstrap state into the persistent `dev` azd environment.
  Preserved the original state lineage and all four Azure resource IDs, with a
  secure ignored backup. Removed the obsolete local tfvars input file.
- Reviewed `azd provision bootstrap --preview` and
  `azd provision application --preview`: no resource creates, replacements,
  or deletions; only bootstrap output renames and the application location output.
- Ran `azd provision --no-prompt` successfully. azd provisioned the `bootstrap`
  layer before `application`; both reported zero resource additions, changes,
  or deletions. No application services were created.
- Confirmed azd-rendered Terraform inputs contain the current tenant's tag values,
  both live taggable resources retain them, and shared keys/anonymous blobs remain
  disabled.
- Verified the application state blob exists and can be listed using Entra RBAC.
  Confirmed the renamed bootstrap outputs persist in azd's saved state.
- Ran `azd hooks run preprovision --no-prompt`; the project check hook passed.

The azd provisioning changes were committed as `288b85b` after local and Azure
verification, pushed to `main`, and verified in the GitHub Actions run above.
All bootstrap acceptance tasks are complete; archival may now proceed.
