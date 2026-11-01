locals {
  count  = var.enabled ? 1 : 0
  name   = "web-${trim(substr("newsloom-${var.environment_name}", 0, 23), "-")}"
  origin = var.enabled ? "https://${local.name}.${data.azurerm_container_app_environment.existing[0].default_domain}" : ""
}
data "azuread_client_config" "current" {
  count = local.count
  lifecycle {
    postcondition {
      condition     = lower(self.tenant_id) == lower(var.tenant_id)
      error_message = "SPA operations must use the configured tenant."
    }
  }
}
data "azurerm_container_app_environment" "existing" {
  count               = local.count
  name                = basename(var.container_app_environment_id)
  resource_group_name = var.resource_group_name
  lifecycle {
    postcondition {
      condition     = self.id == var.container_app_environment_id
      error_message = "Use the exact retained ACA environment."
    }
  }
}
data "azuread_service_principal" "agent" {
  count     = local.count
  object_id = var.agent_api_principal_id
  lifecycle {
    postcondition {
      condition = (self.client_id == var.agent_api_client_id &&
        self.application_tenant_id == var.tenant_id && self.account_enabled &&
        try(self.oauth2_permission_scope_ids["news.agent"], "") == var.agent_scope_id &&
      length(self.oauth2_permission_scope_ids) == 1 && length(self.app_role_ids) == 0)
      error_message = "Only the existing same-tenant delegated news.agent API is permitted."
    }
  }
}
data "azuread_service_principal" "mcp" {
  count     = var.news_enabled ? 1 : 0
  object_id = var.mcp_api_principal_id
  lifecycle {
    postcondition {
      condition = (
        self.client_id == var.mcp_api_client_id &&
        self.application_tenant_id == var.tenant_id && self.account_enabled &&
        try(self.oauth2_permission_scope_ids["news.read"], "") == var.mcp_scope_id &&
        length(self.oauth2_permission_scope_ids) == 1 && length(self.app_role_ids) == 0 &&
        self.client_id != var.agent_api_client_id
      )
      error_message = "Only the existing separate same-tenant delegated MCP resource is allowed."
    }
  }
}
resource "azuread_application" "client" {
  count                          = local.count
  display_name                   = "newsloom-${var.environment_name}-ui"
  sign_in_audience               = "AzureADMyOrg"
  fallback_public_client_enabled = false
  owners                         = [data.azuread_client_config.current[0].object_id]
  single_page_application {
    redirect_uris = ["${local.origin}/auth/callback", "${local.origin}/"]
  }
  required_resource_access {
    resource_app_id = var.agent_api_client_id
    resource_access {
      id   = var.agent_scope_id
      type = "Scope"
    }
  }
  dynamic "required_resource_access" {
    for_each = var.news_enabled ? [1] : []
    content {
      resource_app_id = var.mcp_api_client_id
      resource_access {
        id   = var.mcp_scope_id
        type = "Scope"
      }
    }
  }
  lifecycle {
    prevent_destroy = true
    postcondition {
      condition     = self.client_id != var.agent_api_client_id
      error_message = "The SPA cannot adopt the agent API application."
    }
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
resource "azuread_service_principal_delegated_permission_grant" "agent" {
  count                                = var.enabled && var.consent_enabled ? 1 : 0
  service_principal_object_id          = azuread_service_principal.client[0].object_id
  resource_service_principal_object_id = data.azuread_service_principal.agent[0].object_id
  claim_values                         = ["news.agent"]
}
resource "azuread_service_principal_delegated_permission_grant" "mcp" {
  count                                = var.news_enabled && var.consent_enabled ? 1 : 0
  service_principal_object_id          = azuread_service_principal.client[0].object_id
  resource_service_principal_object_id = data.azuread_service_principal.mcp[0].object_id
  claim_values                         = ["news.read"]
}
output "UI_CLIENT_ID" {
  value = try(azuread_application.client[0].client_id, "")
}
output "UI_ORIGIN" {
  value = local.origin
}
