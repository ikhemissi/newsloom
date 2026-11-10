mock_provider "azurerm" {
  mock_resource "azurerm_storage_account" {
    defaults = {
      id = "/subscriptions/test/resourceGroups/rg-newsloom-test/providers/Microsoft.Storage/storageAccounts/stnlbaktest"
    }
  }
  mock_data "azurerm_client_config" {
    defaults = {
      object_id = join("-", ["00000000", "0000", "0000", "0000", "000000000001"])
    }
  }
}

variables {
  subscription_id      = join("-", ["00000000", "0000", "0000", "0000", "000000000000"])
  environment_name     = "test"
  resource_group_name  = "rg-newsloom-test"
  location             = "francecentral"
  registry_id          = "/subscriptions/test/resourceGroups/test/providers/Microsoft.ContainerRegistry/registries/existing"
  postgres_server_name = "psql-newsloom-test"
  workload_identities_base64 = base64encode(jsonencode({
    mcp = {
      id           = "/subscriptions/test/resourceGroups/test/providers/Microsoft.ManagedIdentity/userAssignedIdentities/mcp"
      client_id    = join("-", ["00000000", "0000", "0000", "0000", "000000000004"])
      principal_id = join("-", ["00000000", "0000", "0000", "0000", "000000000005"])
    }
  }))
}

run "export_storage_is_entra_only_immutable_and_locked" {
  command = plan
  assert {
    condition = (
      azurerm_storage_account.backup.shared_access_key_enabled == false &&
      azurerm_storage_account.backup.allow_nested_items_to_be_public == false &&
      azurerm_storage_account.backup.account_replication_type == "ZRS" &&
      azurerm_storage_account.backup.min_tls_version == "TLS1_2" &&
      length(azurerm_storage_account.backup.name) <= 24 &&
      azurerm_storage_container.postgres.container_access_type == "private" &&
      azurerm_storage_container_immutability_policy.postgres.immutability_period_in_days == 30 &&
      azurerm_storage_container_immutability_policy.postgres.locked == false &&
      azurerm_storage_management_policy.backup.rule[0].actions[0].base_blob[0].delete_after_days_since_creation_greater_than == 60 &&
      azurerm_management_lock.database.lock_level == "CanNotDelete" &&
      endswith(azurerm_management_lock.database.scope, "/flexibleServers/psql-newsloom-test") &&
      azurerm_management_lock.backup.lock_level == "CanNotDelete"
    )
    error_message = "Exports need Entra-only, private, immutable, expiring storage and both delete locks."
  }
}

run "operations_grants_are_minimal" {
  command = apply
  assert {
    condition = (
      toset(azurerm_role_definition.power.permissions[0].actions) == toset([
        "Microsoft.DBforPostgreSQL/flexibleServers/read",
        "Microsoft.DBforPostgreSQL/flexibleServers/start/action",
        "Microsoft.DBforPostgreSQL/flexibleServers/stop/action",
      ]) &&
      length(azurerm_role_definition.power.permissions[0].data_actions) == 0 &&
      azurerm_role_assignment.power.scope == "/subscriptions/${var.subscription_id}/resourceGroups/rg-newsloom-test/providers/Microsoft.DBforPostgreSQL/flexibleServers/psql-newsloom-test" &&
      azurerm_role_assignment.tags.role_definition_name == "Tag Contributor" &&
      azurerm_role_assignment.writer.role_definition_name == "Storage Blob Data Contributor" &&
      endswith(azurerm_role_assignment.writer.scope, "/blobServices/default/containers/postgres") &&
      azurerm_role_assignment.operator.role_definition_name == "Storage Blob Data Reader" &&
      endswith(azurerm_role_assignment.operator.scope, "/blobServices/default/containers/postgres") &&
      azurerm_role_assignment.registry.role_definition_name == "AcrPull"
    )
    error_message = "Operations may only power the server, merge tags, write exports and pull images."
  }
}

run "exports_outlive_immutability" {
  command = plan
  variables {
    backup_retention_days = 30
  }
  expect_failures = [var.backup_retention_days]
}

run "snapshots_are_private_short_lived_and_written_only_by_mcp" {
  command = apply
  assert {
    condition = (
      azurerm_storage_container.snapshots.container_access_type == "private" &&
      azurerm_role_assignment.snapshots.principal_id == join("-", ["00000000", "0000", "0000", "0000", "000000000005"]) &&
      azurerm_role_assignment.snapshots.role_definition_name == "Storage Blob Data Contributor" &&
      endswith(azurerm_role_assignment.snapshots.scope, "/blobServices/default/containers/snapshots") &&
      azurerm_storage_management_policy.backup.rule[1].actions[0].base_blob[0].delete_after_days_since_modification_greater_than == 7 &&
      endswith(output.SNAPSHOT_URL, "snapshots/latest.json.gz")
    )
    error_message = "Only the MCP identity writes the private, 7-day read snapshot."
  }
}
