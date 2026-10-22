# Azure state bootstrap

## Boundaries

This runbook implements the
[OpenSpec state-bootstrap contract](../openspec/changes/bootstrap/specs/repository-foundation/spec.md#requirement-secretless-remote-state-bootstrap).
Its release boundaries are defined by the
[OpenSpec delivery contract](../openspec/changes/bootstrap/specs/repository-foundation/spec.md#requirement-honest-ordered-delivery),
not by this procedure. The commands below affect Azure only when explicitly run.

State infrastructure is a separate one-off [Terraform root](../infra/bootstrap/),
with local state to avoid the circular dependency of a backend creating itself.
Preserve that ignored local bootstrap state securely; do not rerun from an empty
state against an existing account. Import existing resources if recovering state.
The implementation's `prevent_destroy` guards cover the account, container, and
resource group.

## Prerequisites

- Run `bash scripts/check.sh` successfully first.
- Sign in with Azure CLI and select the intended subscription.
- Have permission to create the resource group/storage account and assign
  `Storage Blob Data Contributor` (for example, Contributor plus RBAC Administrator
  at the appropriate scope).
- Ensure the `Microsoft.Storage` resource provider is registered. Terraform
  automatic provider registration is disabled rather than requesting broad rights.

```bash
az login
az account set --subscription "<subscription-id>"
az provider register --namespace Microsoft.Storage --wait
azd config set auth.useAzCliAuth true
```

## One-off state creation

Copy [bootstrap.tfvars.example](../infra/bootstrap/bootstrap.tfvars.example) to
`infra/bootstrap/bootstrap.auto.tfvars` and replace its placeholders locally.
That file, local state, saved plans, and azd environment values are ignored.
Choose a globally unique storage account name; retain the chosen names.

```bash
terraform -chdir=infra/bootstrap init
terraform -chdir=infra/bootstrap validate
terraform -chdir=infra/bootstrap plan -out=bootstrap.tfplan
terraform -chdir=infra/bootstrap apply bootstrap.tfplan
```

Inspect the saved plan before applying. This creates only:

- A dedicated state resource group and Standard LRS StorageV2 account.
- HTTPS/TLS 1.2, OAuth preferred, and no anonymous blobs; authorization follows
  the linked state contract.
- A private state container, blob versioning, and 30-day soft delete.
- `Storage Blob Data Contributor` on the account for the currently signed-in
  principal. Other principals require an explicit, least-privilege role assignment.

The public endpoint is intentional in v1; RBAC still protects the data.
RBAC propagation may briefly return 403. Wait for propagation and retry the same
operation without changing its authorization method.

## Verify data-plane RBAC and persist azd configuration

```bash
STATE_ACCOUNT="$(terraform -chdir=infra/bootstrap output -raw storage_account_name)"
STATE_CONTAINER="$(terraform -chdir=infra/bootstrap output -raw container_name)"
STATE_GROUP="$(terraform -chdir=infra/bootstrap output -raw resource_group_name)"

az storage account show --resource-group "$STATE_GROUP" --name "$STATE_ACCOUNT" \
  --query '{sharedKeys:allowSharedKeyAccess,anonymousBlobs:allowBlobPublicAccess}' -o json
az storage blob list --account-name "$STATE_ACCOUNT" \
  --container-name "$STATE_CONTAINER" --auth-mode login -o table
```

For this configuration, the two flag outputs are `false` and listing the initially
empty container succeeds. Exercise the state contract's data-plane acceptance
scenario with a disposable non-secret probe:

```bash
PROBE="$(mktemp)"
PROBE_NAME="bootstrap-rbac-probe-$(uv run python -c 'from uuid import uuid4; print(uuid4())')"
printf 'newsloom-state-rbac-probe\n' > "$PROBE"
az storage blob upload --account-name "$STATE_ACCOUNT" --container-name "$STATE_CONTAINER" \
  --name "$PROBE_NAME" --file "$PROBE" --auth-mode login
az storage blob download --account-name "$STATE_ACCOUNT" --container-name "$STATE_CONTAINER" \
  --name "$PROBE_NAME" --file "$PROBE.download" --auth-mode login
cmp "$PROBE" "$PROBE.download"
LEASE_ID="$(uv run python -c 'from uuid import uuid4; print(uuid4())')"
az storage blob lease acquire --account-name "$STATE_ACCOUNT" \
  --container-name "$STATE_CONTAINER" --blob-name "$PROBE_NAME" \
  --proposed-lease-id "$LEASE_ID" --lease-duration 15 --auth-mode login --output none
az storage blob lease release --account-name "$STATE_ACCOUNT" \
  --container-name "$STATE_CONTAINER" --blob-name "$PROBE_NAME" \
  --lease-id "$LEASE_ID" --auth-mode login
az storage blob delete --account-name "$STATE_ACCOUNT" --container-name "$STATE_CONTAINER" \
  --name "$PROBE_NAME" --auth-mode login
rm -- "$PROBE" "$PROBE.download"
```

Record outcomes against the linked OpenSpec acceptance scenario. Set up one
persistent azd environment (run `env new` only once):

```bash
azd env new dev
azd env set AZURE_SUBSCRIPTION_ID "$(az account show --query id -o tsv)"
azd env set AZURE_LOCATION "<azure-region>"
azd env set RS_RESOURCE_GROUP "$STATE_GROUP"
azd env set RS_STORAGE_ACCOUNT "$STATE_ACCOUNT"
azd env set RS_CONTAINER_NAME "$STATE_CONTAINER"
```

The [backend configuration](../infra/provider.conf.json) is expanded by azd and
uses a separate state key for each environment. Use azd for the
[main Terraform root](../infra/) so that it resolves this backend configuration;
the raw Terraform commands above apply only to the separate bootstrap root.
For later sessions use `azd env select dev`, not a replacement environment.

For application provisioning scope and ordering, use the
[Phase 1 delivery plan](prd-1.md#delivery-plan) and its linked capabilities.
