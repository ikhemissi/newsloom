locals {
  count  = var.enabled ? 1 : 0
  prefix = "newsloom-${var.environment_name}"
  group  = "/subscriptions/${var.subscription_id}/resourceGroups/${var.resource_group_name}"
  scope  = var.adoption.scope_id != "" ? var.adoption.scope_id : uuidv5("dns", "${local.prefix}/news.agent")
}

data "azuread_client_config" "current" {
  count = local.count
  lifecycle {
    postcondition {
      condition     = lower(self.tenant_id) == lower(var.tenant_id)
      error_message = "Directory operations must use the configured single tenant."
    }
  }
}
data "azurerm_client_config" "current" {
  count = local.count
  lifecycle {
    postcondition {
      condition     = lower(self.tenant_id) == lower(var.tenant_id) && lower(self.subscription_id) == lower(var.subscription_id)
      error_message = "The agent identity must belong to the configured tenant and subscription."
    }
  }
}
data "azuread_service_principal" "mcp" {
  count     = local.count
  object_id = var.mcp_api_principal_id
  lifecycle {
    postcondition {
      condition = (
        self.client_id == var.mcp_api_client_id &&
        self.account_enabled &&
        self.application_tenant_id == var.tenant_id &&
        try(self.oauth2_permission_scope_ids["news.read"], "") == var.mcp_scope_id &&
        length(self.oauth2_permission_scope_ids) == 1 &&
        length(self.app_role_ids) == 0
      )
      error_message = "MCP must be the exact enabled same-tenant delegated-only news.read resource."
    }
  }
}

resource "azurerm_user_assigned_identity" "agent" {
  count               = local.count
  name                = "id-${local.prefix}-agent"
  resource_group_name = var.resource_group_name
  location            = var.location
  tags                = merge(var.tags, { azd-env-name = var.environment_name })
  lifecycle {
    prevent_destroy = true
  }
}
resource "azuread_application" "api" {
  count            = local.count
  display_name     = "${local.prefix}-agent-api"
  sign_in_audience = "AzureADMyOrg"
  owners           = [data.azuread_client_config.current[0].object_id]
  api {
    requested_access_token_version = 2
    oauth2_permission_scope {
      id                         = local.scope
      value                      = "news.agent"
      type                       = "User"
      enabled                    = true
      admin_consent_display_name = "Invoke Newsloom agent"
      admin_consent_description  = "Invoke the bounded news demonstrator as the signed-in user."
      user_consent_display_name  = "Invoke Newsloom agent"
      user_consent_description   = "Use your delegated identity for the recent-news demonstrator."
    }
  }
  required_resource_access {
    resource_app_id = var.mcp_api_client_id
    resource_access {
      id   = var.mcp_scope_id
      type = "Scope"
    }
  }
  lifecycle {
    prevent_destroy = true
    ignore_changes  = [identifier_uris]
    postcondition {
      condition     = self.client_id != var.mcp_api_client_id
      error_message = "The middle tier must never adopt the MCP API registration."
    }
  }
}
resource "azuread_application_identifier_uri" "api" {
  count          = local.count
  application_id = azuread_application.api[0].id
  identifier_uri = "api://${azuread_application.api[0].client_id}"
}
resource "azuread_application" "client" {
  count                          = local.count
  display_name                   = "${local.prefix}-agent-acceptance"
  sign_in_audience               = "AzureADMyOrg"
  owners                         = [data.azuread_client_config.current[0].object_id]
  fallback_public_client_enabled = true
  public_client {
    redirect_uris = var.redirect_uris
  }
  required_resource_access {
    resource_app_id = azuread_application.api[0].client_id
    resource_access {
      id   = local.scope
      type = "Scope"
    }
  }
  lifecycle {
    prevent_destroy = true
    postcondition {
      condition     = self.client_id != var.mcp_api_client_id && self.client_id != azuread_application.api[0].client_id
      error_message = "The PKCE client must be separate from both resource registrations."
    }
  }
}
resource "azuread_service_principal" "api" {
  count     = local.count
  client_id = azuread_application.api[0].client_id
  owners    = [data.azuread_client_config.current[0].object_id]
  lifecycle {
    prevent_destroy = true
  }
}
resource "azuread_service_principal" "client" {
  count     = local.count
  client_id = azuread_application.client[0].client_id
  owners    = [data.azuread_client_config.current[0].object_id]
  lifecycle {
    prevent_destroy = true
  }
}
resource "azuread_application_federated_identity_credential" "managed_identity" {
  count          = local.count
  application_id = azuread_application.api[0].id
  display_name   = "agent-managed-identity"
  description    = "Exact same-tenant user-assigned identity for secretless OBO."
  issuer         = "https://login.microsoftonline.com/${var.tenant_id}/v2.0"
  audiences      = ["api://AzureADTokenExchange"]
  subject        = azurerm_user_assigned_identity.agent[0].principal_id
  depends_on     = [data.azurerm_client_config.current]
}
resource "azuread_service_principal_delegated_permission_grant" "mcp" {
  count                                = var.enabled && var.consent_enabled ? 1 : 0
  service_principal_object_id          = azuread_service_principal.api[0].object_id
  resource_service_principal_object_id = data.azuread_service_principal.mcp[0].object_id
  claim_values                         = ["news.read"]
}
resource "azuread_service_principal_delegated_permission_grant" "client" {
  count                                = var.enabled && var.consent_enabled ? 1 : 0
  service_principal_object_id          = azuread_service_principal.client[0].object_id
  resource_service_principal_object_id = azuread_service_principal.api[0].object_id
  claim_values                         = ["news.agent"]
}
resource "azurerm_role_definition" "chat" {
  count             = local.count
  name              = "${local.prefix}-agent-chat"
  scope             = local.group
  assignable_scopes = [local.group]
  description       = "Only chat completions; no embeddings, screening, database or management access."
  permissions {
    actions      = []
    data_actions = ["Microsoft.CognitiveServices/accounts/OpenAI/deployments/chat/completions/action"]
  }
}
resource "azurerm_role_assignment" "chat" {
  count                            = local.count
  scope                            = var.model_account_id
  role_definition_id               = azurerm_role_definition.chat[0].role_definition_resource_id
  principal_id                     = azurerm_user_assigned_identity.agent[0].principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}
resource "azurerm_role_assignment" "registry" {
  count                            = local.count
  scope                            = var.registry_id
  role_definition_name             = "AcrPull"
  principal_id                     = azurerm_user_assigned_identity.agent[0].principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}
resource "azurerm_role_assignment" "telemetry" {
  count                            = local.count
  scope                            = var.applicationinsights_id
  role_definition_name             = "Monitoring Metrics Publisher"
  principal_id                     = azurerm_user_assigned_identity.agent[0].principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}

output "AGENT_IDENTITY_BASE64" {
  value = var.enabled ? base64encode(jsonencode({
    id           = azurerm_user_assigned_identity.agent[0].id
    client_id    = azurerm_user_assigned_identity.agent[0].client_id
    principal_id = azurerm_user_assigned_identity.agent[0].principal_id
  })) : ""
}
output "AGENT_API_CLIENT_ID" {
  value = try(azuread_application.api[0].client_id, "")
}
output "AGENT_PUBLIC_CLIENT_ID" {
  value = try(azuread_application.client[0].client_id, "")
}
output "AGENT_INVOKE_SCOPE" {
  value = var.enabled ? "api://${azuread_application.api[0].client_id}/news.agent" : ""
}
