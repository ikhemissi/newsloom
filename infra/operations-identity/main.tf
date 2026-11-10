data "azurerm_client_config" "current" {}

locals {
  prefix    = "newsloom-${var.environment_name}"
  group     = "/subscriptions/${var.subscription_id}/resourceGroups/${var.resource_group_name}"
  server_id = "${local.group}/providers/Microsoft.DBforPostgreSQL/flexibleServers/${var.postgres_server_name}"
  tags      = merge(var.tags, { azd-env-name = var.environment_name })
  container = "${azurerm_storage_account.backup.id}/blobServices/default/containers/${azurerm_storage_container.postgres.name}"
}

resource "azurerm_user_assigned_identity" "operations" {
  name                = "id-${local.prefix}-operations"
  resource_group_name = var.resource_group_name
  location            = var.location
  tags                = local.tags
}

resource "azurerm_role_definition" "power" {
  name              = "${local.prefix}-database-power"
  scope             = local.group
  description       = "Operations: read, start and stop the Newsloom PostgreSQL server only."
  assignable_scopes = [local.server_id]
  permissions {
    actions = [
      "Microsoft.DBforPostgreSQL/flexibleServers/read",
      "Microsoft.DBforPostgreSQL/flexibleServers/start/action",
      "Microsoft.DBforPostgreSQL/flexibleServers/stop/action",
    ]
    data_actions = []
  }
}

resource "azurerm_role_assignment" "power" {
  scope                            = local.server_id
  role_definition_id               = azurerm_role_definition.power.role_definition_resource_id
  principal_id                     = azurerm_user_assigned_identity.operations.principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}

# Lets the wake job merge back the governance tags every deployment already sets.
resource "azurerm_role_assignment" "tags" {
  scope                            = local.group
  role_definition_name             = "Tag Contributor"
  principal_id                     = azurerm_user_assigned_identity.operations.principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}

resource "azurerm_role_assignment" "registry" {
  scope                            = var.registry_id
  role_definition_name             = "AcrPull"
  principal_id                     = azurerm_user_assigned_identity.operations.principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}

resource "azurerm_storage_account" "backup" {
  name                            = "stnlbak${substr(sha1(local.group), 0, 12)}"
  resource_group_name             = var.resource_group_name
  location                        = var.location
  account_kind                    = "StorageV2"
  account_tier                    = "Standard"
  account_replication_type        = "ZRS"
  min_tls_version                 = "TLS1_2"
  https_traffic_only_enabled      = true
  shared_access_key_enabled       = false
  default_to_oauth_authentication = true
  allow_nested_items_to_be_public = false
  public_network_access           = "Enabled"
  tags                            = local.tags

  blob_properties {
    delete_retention_policy {
      days = 14
    }
    container_delete_retention_policy {
      days = 14
    }
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "azurerm_storage_container" "postgres" {
  name                  = "postgres"
  storage_account_id    = azurerm_storage_account.backup.id
  container_access_type = "private"
}

resource "azurerm_storage_container_immutability_policy" "postgres" {
  storage_container_resource_manager_id = local.container
  immutability_period_in_days           = var.backup_immutable_days
  protected_append_writes_enabled       = false
  locked                                = false
}

resource "azurerm_storage_management_policy" "backup" {
  storage_account_id = azurerm_storage_account.backup.id
  rule {
    name    = "expire-exports"
    enabled = true
    filters {
      blob_types   = ["blockBlob"]
      prefix_match = ["postgres/postgres/"]
    }
    actions {
      base_blob {
        delete_after_days_since_creation_greater_than = var.backup_retention_days
      }
    }
  }
}

resource "azurerm_role_assignment" "writer" {
  scope                            = local.container
  role_definition_name             = "Storage Blob Data Contributor"
  principal_id                     = azurerm_user_assigned_identity.operations.principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}

# The deploying operator reads exports for restore drills.
resource "azurerm_role_assignment" "operator" {
  scope                = local.container
  role_definition_name = "Storage Blob Data Reader"
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "azurerm_management_lock" "database" {
  name       = "newsloom-keep-database"
  scope      = local.server_id
  lock_level = "CanNotDelete"
  notes      = "Holds application data; remove deliberately before any deletion."
}

resource "azurerm_management_lock" "backup" {
  name       = "newsloom-keep-backups"
  scope      = azurerm_storage_account.backup.id
  lock_level = "CanNotDelete"
  notes      = "Holds database exports; remove deliberately before any deletion."
}

output "OPERATIONS_IDENTITY_BASE64" {
  value = base64encode(jsonencode({
    id           = azurerm_user_assigned_identity.operations.id
    client_id    = azurerm_user_assigned_identity.operations.client_id
    principal_id = azurerm_user_assigned_identity.operations.principal_id
  }))
}
output "BACKUP_ACCOUNT_URL" {
  value = azurerm_storage_account.backup.primary_blob_endpoint
}
output "BACKUP_CONTAINER" {
  value = azurerm_storage_container.postgres.name
}
