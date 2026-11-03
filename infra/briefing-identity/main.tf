locals {
  count  = var.enabled ? 1 : 0
  prefix = "newsloom-${var.environment_name}"
  group  = "/subscriptions/${var.subscription_id}/resourceGroups/${var.resource_group_name}"
  tags   = merge(var.tags, { azd-env-name = var.environment_name })
}

resource "azurerm_user_assigned_identity" "briefing" {
  count               = local.count
  name                = "id-${local.prefix}-briefing"
  resource_group_name = var.resource_group_name
  location            = var.location
  tags                = local.tags
}

# Azure OpenAI data-plane custom roles support account scope, not deployment isolation.
resource "azurerm_role_definition" "chat" {
  count             = local.count
  name              = "${local.prefix}-briefing-chat"
  scope             = local.group
  description       = "Briefing: chat completions only; no embeddings or management operations."
  assignable_scopes = [local.group]
  permissions {
    actions      = []
    data_actions = ["Microsoft.CognitiveServices/accounts/OpenAI/deployments/chat/completions/action"]
  }
}
resource "azurerm_role_assignment" "chat" {
  count                            = local.count
  scope                            = var.model_account_id
  role_definition_id               = azurerm_role_definition.chat[0].role_definition_resource_id
  principal_id                     = azurerm_user_assigned_identity.briefing[0].principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}
resource "azurerm_role_assignment" "registry" {
  count                            = local.count
  scope                            = var.registry_id
  role_definition_name             = "AcrPull"
  principal_id                     = azurerm_user_assigned_identity.briefing[0].principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}
resource "azurerm_role_assignment" "telemetry" {
  count                            = local.count
  scope                            = var.applicationinsights_id
  role_definition_name             = "Monitoring Metrics Publisher"
  principal_id                     = azurerm_user_assigned_identity.briefing[0].principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}
resource "azurerm_cognitive_deployment" "briefing" {
  count                  = local.count
  name                   = var.generation_deployment
  cognitive_account_id   = var.model_account_id
  version_upgrade_option = "NoAutoUpgrade"
  model {
    format  = "OpenAI"
    name    = var.generation_model
    version = var.generation_version
  }
  sku {
    name     = var.generation_sku
    capacity = 10
  }
}
output "BRIEFING_IDENTITY_BASE64" {
  value = var.enabled ? base64encode(jsonencode({
    id           = azurerm_user_assigned_identity.briefing[0].id
    client_id    = azurerm_user_assigned_identity.briefing[0].client_id
    principal_id = azurerm_user_assigned_identity.briefing[0].principal_id
  })) : ""
}
output "BRIEFING_MODEL_DEPLOYMENT_ID" {
  value = var.enabled ? azurerm_cognitive_deployment.briefing[0].id : ""
}
