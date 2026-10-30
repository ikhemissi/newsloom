locals {
  data_enabled    = var.enabled && var.data_resources.enabled
  storage_name    = var.data_resources.storage_name != "" ? var.data_resources.storage_name : "stnleval${substr(sha256(var.model_account_id), 0, 12)}"
  storage_id      = "${local.group_id}/providers/Microsoft.Storage/storageAccounts/${local.storage_name}"
  connection_name = var.data_resources.connection_name != "" ? var.data_resources.connection_name : "newsloom-evaluation-storage"
  data_grants = local.data_enabled ? merge({
    storage = {
      parent_id      = local.storage_id
      name           = var.data_resources.storage_grant_name != "" ? var.data_resources.storage_grant_name : uuidv5("url", "${local.storage_id}/${azurerm_cognitive_account_project.evaluation[0].identity[0].principal_id}/${var.data_resources.storage_role_id}")
      principal_id   = azurerm_cognitive_account_project.evaluation[0].identity[0].principal_id
      principal_type = "ServicePrincipal"
      role_id        = var.data_resources.storage_role_id
    }
    account_user = {
      parent_id      = var.model_account_id
      name           = var.data_resources.account_user_grant_name != "" ? var.data_resources.account_user_grant_name : uuidv5("url", "${var.model_account_id}/foundry-user/${var.operator_principal_id}")
      principal_id   = var.operator_principal_id
      principal_type = "User"
      role_id        = var.foundry_user_role_id
    }
    account_manager = {
      parent_id      = var.model_account_id
      name           = var.data_resources.account_manager_grant_name != "" ? var.data_resources.account_manager_grant_name : uuidv5("url", "${var.model_account_id}/foundry-project-manager/${var.operator_principal_id}")
      principal_id   = var.operator_principal_id
      principal_type = "User"
      role_id        = var.foundry_project_manager_role_id
    }
    }, var.data_resources.retain_experimental_appinsights_grants ? {
    appinsights_reader = {
      parent_id      = var.data_resources.appinsights_id
      name           = var.data_resources.appinsights_reader_name
      principal_id   = azurerm_cognitive_account_project.evaluation[0].identity[0].principal_id
      principal_type = "ServicePrincipal"
      role_id        = var.data_resources.appinsights_reader_role_id
    }
    appinsights_publisher = {
      parent_id      = var.data_resources.appinsights_id
      name           = var.data_resources.appinsights_publisher_name
      principal_id   = azurerm_cognitive_account_project.evaluation[0].identity[0].principal_id
      principal_type = "ServicePrincipal"
      role_id        = var.data_resources.appinsights_publisher_role_id
    }
  } : {}) : {}
}

# ARM-only management avoids account keys and unrelated operator data-plane grants.
resource "azapi_resource" "evaluation_storage" {
  count     = local.data_enabled ? 1 : 0
  type      = "Microsoft.Storage/storageAccounts@2024-01-01"
  parent_id = local.group_id
  name      = local.storage_name
  location  = var.location
  tags      = merge(var.tags, { azd-env-name = var.environment_name })
  body = {
    kind = "StorageV2"
    sku  = { name = "Standard_LRS" }
    properties = {
      allowSharedKeyAccess     = false
      allowBlobPublicAccess    = false
      minimumTlsVersion        = "TLS1_2"
      supportsHttpsTrafficOnly = true
      networkAcls = {
        bypass              = "None"
        defaultAction       = "Allow"
        ipRules             = []
        virtualNetworkRules = []
      }
    }
  }
  lifecycle {
    prevent_destroy = true
  }
  depends_on = [data.azurerm_client_config.current]
}

resource "azapi_resource" "evaluation_storage_connection" {
  count     = local.data_enabled ? 1 : 0
  type      = "Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview"
  parent_id = azurerm_cognitive_account_project.evaluation[0].id
  name      = local.connection_name
  # The live, verified auth type is missing from AzAPI 2.13's embedded schema.
  schema_validation_enabled = false
  # Private endpoint status is reported by the service, not configured here.
  ignore_body_changes = ["properties.peStatus", "properties.peRequirement"]
  response_export_values = [
    "properties.authType", "properties.category", "properties.target",
    "properties.isSharedToAll", "properties.isDefault", "properties.metadata.ResourceId",
  ]
  body = {
    properties = {
      category                    = "AzureStorageAccount"
      authType                    = "ProjectManagedIdentity"
      target                      = "https://${local.storage_name}.blob.core.windows.net/"
      isSharedToAll               = false
      isDefault                   = true
      useWorkspaceManagedIdentity = false
      sharedUserList              = []
      metadata = {
        ApiType     = "Azure"
        ResourceId  = local.storage_id
        displayName = local.storage_name
      }
    }
  }
  lifecycle {
    prevent_destroy = true
    postcondition {
      condition = (
        self.output.properties.authType == "ProjectManagedIdentity" &&
        self.output.properties.category == "AzureStorageAccount" &&
        self.output.properties.target == "https://${local.storage_name}.blob.core.windows.net/" &&
        self.output.properties.isSharedToAll == false &&
        self.output.properties.isDefault == true &&
        lower(self.output.properties.metadata.ResourceId) == lower(local.storage_id)
      )
      error_message = "Readback must preserve the exact project-managed-identity storage connection."
    }
  }
  depends_on = [azapi_resource.evaluation_storage, azapi_resource.data_grants]
}

resource "azapi_resource" "data_grants" {
  for_each  = local.data_grants
  type      = "Microsoft.Authorization/roleAssignments@2022-04-01"
  parent_id = each.value.parent_id
  name      = each.value.name
  body = {
    properties = {
      principalId      = each.value.principal_id
      principalType    = each.value.principal_type
      roleDefinitionId = "/subscriptions/${var.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/${each.value.role_id}"
    }
  }
  depends_on = [data.azurerm_client_config.current, azapi_resource.evaluation_storage]
}

import {
  for_each = local.data_enabled && var.data_resources.import_existing ? { existing = local.storage_id } : {}
  to       = azapi_resource.evaluation_storage[0]
  id       = "${each.value}?api-version=2024-01-01"
}

import {
  for_each = local.data_enabled && var.data_resources.import_existing ? { existing = "${var.model_account_id}/projects/${local.name}/connections/${local.connection_name}" } : {}
  to       = azapi_resource.evaluation_storage_connection[0]
  id       = "${each.value}?api-version=2025-04-01-preview"
}

import {
  for_each = var.data_resources.import_existing ? local.data_grants : {}
  to       = azapi_resource.data_grants[each.key]
  id       = "${each.value.parent_id}/providers/Microsoft.Authorization/roleAssignments/${each.value.name}?api-version=2022-04-01"
}
