mock_provider "azurerm" {}

variables {
  subscription_id      = join("-", ["00000000", "0000", "0000", "0000", "000000000000"])
  location             = "westeurope"
  resource_group_name  = "rg-newsloom-state-test"
  storage_account_name = "stnewsloomstatetest"
  tags = {
    owner   = "test"
    project = "configured-project"
    purpose = "configured-purpose"
  }
}

run "state_is_secretless_and_recoverable" {
  command = plan

  assert {
    condition = (
      azurerm_storage_account.state.shared_access_key_enabled == false &&
      azurerm_storage_account.state.default_to_oauth_authentication == true &&
      azurerm_storage_account.state.allow_nested_items_to_be_public == false &&
      azurerm_storage_container.state.container_access_type == "private"
    )
    error_message = "State must use OAuth/RBAC without shared keys or anonymous blob access."
  }

  assert {
    condition = (
      azurerm_storage_account.state.https_traffic_only_enabled == true &&
      azurerm_storage_account.state.min_tls_version == "TLS1_2" &&
      azurerm_storage_account.state.public_network_access == "Enabled"
    )
    error_message = "Bootstrap must retain its intentional HTTPS-only public endpoint."
  }

  assert {
    condition = (
      azurerm_storage_account.state.blob_properties[0].versioning_enabled == true &&
      azurerm_storage_account.state.blob_properties[0].delete_retention_policy[0].days == 30 &&
      azurerm_storage_account.state.blob_properties[0].container_delete_retention_policy[0].days == 30
    )
    error_message = "State needs versioning and soft-delete recovery."
  }

  assert {
    condition     = azurerm_role_assignment.state_writer.role_definition_name == "Storage Blob Data Contributor"
    error_message = "The operator must receive the blob data-plane role rather than account-key access."
  }

  assert {
    condition = (
      azurerm_resource_group.state.tags == var.tags &&
      azurerm_storage_account.state.tags == var.tags &&
      azurerm_storage_container.state.name == "tfstate"
    )
    error_message = "All taggable resources must preserve the supplied tag map and container default."
  }

  assert {
    condition = (
      output.RS_RESOURCE_GROUP == azurerm_resource_group.state.name &&
      output.RS_STORAGE_ACCOUNT == azurerm_storage_account.state.name &&
      output.RS_CONTAINER_NAME == azurerm_storage_container.state.name
    )
    error_message = "Bootstrap outputs must supply the azd application layer's backend configuration."
  }
}

run "reject_invalid_account_name" {
  command = plan

  variables {
    storage_account_name = "Invalid-Account"
  }

  expect_failures = [var.storage_account_name]
}

run "reject_invalid_container_name" {
  command = plan

  variables {
    container_name = "invalid--container"
  }

  expect_failures = [var.container_name]
}
