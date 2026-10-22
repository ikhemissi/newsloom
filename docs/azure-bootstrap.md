# Azure state bootstrap

## Boundaries

This runbook implements the
[OpenSpec state-bootstrap contract](../openspec/changes/bootstrap/specs/repository-foundation/spec.md#requirement-secretless-remote-state-bootstrap).
Its release boundaries are defined by the
[OpenSpec delivery contract](../openspec/changes/bootstrap/specs/repository-foundation/spec.md#requirement-honest-ordered-delivery),
not by this procedure. The commands below affect Azure only when explicitly run.

Provision resources only through azd; Terraform is its IaC engine, not a separate
deployment entry point. The [project](../azure.yaml) has two native Terraform layers:

| Layer | Root | State |
| --- | --- | --- |
| `bootstrap` | [State infrastructure](../infra/bootstrap/) | Local, under `.azure/<environment>/infra/bootstrap/terraform.tfstate` |
| `application` | [Application infrastructure](../infra/) | Entra-authenticated Azure Blob backend; depends on `bootstrap` |

Bootstrap state stays local to avoid a backend creating itself. Preserve the
ignored azd environment and bootstrap state securely; never provision an existing
account from empty state. The implementation's `prevent_destroy` guards cover
the account, container, and resource group.

## Prerequisites

- Run `bash scripts/check.sh` successfully first.
- Use azd 1.36.0 or newer for the native layer workflow.
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

## Configure the persistent environment

For a new project environment, run `azd env new dev` once. For this repository's
existing environment, select `dev` instead; do not create a replacement.
Configure the following inputs using the existing resource names when adopting
resources, or choose stable names and a globally unique storage account name
for a fresh bootstrap:

```bash
azd env select dev
azd env set AZURE_SUBSCRIPTION_ID "$(az account show --query id -o tsv)"
azd env set AZURE_LOCATION "<azure-region>"
azd env set RS_RESOURCE_GROUP "<state-resource-group>"
azd env set RS_STORAGE_ACCOUNT "<globally-unique-account-name>"
azd env set RS_CONTAINER_NAME tfstate
azd env set SECURITY_CONTROL_TAG Ignore
azd env set COST_CONTROL_TAG Ignore
```

Both [bootstrap](../infra/bootstrap/main.tfvars.json) and
[application](../infra/main.tfvars.json) variable templates expand these azd inputs
into Terraform maps. The current tenant may change or remove resources without
`SecurityControl=Ignore` and `CostControl=Ignore`. These are tenant-specific
deployment settings, not Newsloom product requirements. Keep their values in the
azd environment, not in resource definitions. The Terraform roots accept any
common tag map, including an empty one; other tenants can adjust the deployment
templates accordingly. Additional tags belong in the templates' `tags` maps.
Blob containers and role assignments do not support Azure resource tags.

## Adopt existing direct-Terraform state

Skip this section for a fresh bootstrap. The existing resources were initially
created directly with Terraform; adopt their state before the first azd preview.
Do not delete or recreate the resources, and do not copy an empty or unrelated
state over azd's state.

For the existing `dev` environment, if the old state is still at its original
location and the azd destination does not exist:

```bash
mkdir -p .azure/dev/infra/bootstrap
test ! -e .azure/dev/infra/bootstrap/terraform.tfstate &&
  cp -p infra/bootstrap/terraform.tfstate infra/bootstrap/terraform.tfstate.pre-azd &&
  mv infra/bootstrap/terraform.tfstate .azure/dev/infra/bootstrap/terraform.tfstate
chmod 600 .azure/dev/infra/bootstrap/terraform.tfstate
```

Retain the ignored pre-adoption backup securely. After preserving any needed
custom tags in the azd variable template, remove an obsolete
`infra/bootstrap/bootstrap.auto.tfvars` file to avoid maintaining two input sources.
Once adopted, always use azd with the same environment.

## Preview and provision state through azd

```bash
azd provision bootstrap --preview
azd provision bootstrap
```

Review the preview before provisioning. For adopted resources, expect no resource
creates, replacements, or deletions; output-name changes are expected during the
initial adoption. For a fresh bootstrap, this creates only:

- A dedicated state resource group and Standard LRS StorageV2 account.
- HTTPS/TLS 1.2, OAuth preferred, and no anonymous blobs; authorization follows
  the linked state contract.
- A private state container, blob versioning, and 30-day soft delete.
- `Storage Blob Data Contributor` on the account for the currently signed-in
  principal. Other principals require an explicit, least-privilege role assignment.

For the current tenant, confirm both policy-control tags on every taggable
resource in the preview.
The bootstrap outputs persist `RS_RESOURCE_GROUP`, `RS_STORAGE_ACCOUNT`, and
`RS_CONTAINER_NAME` for the dependent application layer.

The public endpoint is intentional in v1; RBAC still protects the data.
RBAC propagation may briefly return 403. Wait for propagation and retry the same
operation without changing its authorization method.

## Verify data-plane RBAC

```bash
STATE_ACCOUNT="$(azd env get-value RS_STORAGE_ACCOUNT)"
STATE_CONTAINER="$(azd env get-value RS_CONTAINER_NAME)"
STATE_GROUP="$(azd env get-value RS_RESOURCE_GROUP)"

az storage account show --resource-group "$STATE_GROUP" --name "$STATE_ACCOUNT" \
  --query '{sharedKeys:allowSharedKeyAccess,anonymousBlobs:allowBlobPublicAccess,tags:tags}' -o json
az group show --name "$STATE_GROUP" --query tags -o json
az storage blob list --account-name "$STATE_ACCOUNT" \
  --container-name "$STATE_CONTAINER" --auth-mode login -o table
```

For this configuration, the two flag outputs are `false`, both governance tags
match the configured values, and listing the container succeeds. Exercise the
state contract's data-plane acceptance
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

Record outcomes against the linked OpenSpec acceptance scenario. For later
sessions, use `azd env select dev`. Once the owning delivery slice is ready,
provision the application layer or all layers:

```bash
azd provision application --preview
azd provision application
# Alternatively, provision both layers in dependency order:
azd provision
```

The [backend configuration](../infra/provider.conf.json) is expanded by azd and
uses a separate application state key for each environment. Terraform commands in
the local check script perform formatting, validation, and mocked tests only;
they are not provisioning commands.

For application provisioning scope and ordering, use the
[Phase 1 delivery plan](prd-1.md#delivery-plan) and its linked capabilities.
