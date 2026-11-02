locals {
  count = var.enabled ? 1 : 0
  name  = "web-${trim(substr("newsloom-${var.environment_name}", 0, 23), "-")}"
  environment = var.enabled ? merge({
    UI_CONFIG_BASE64    = var.config_base64
    AGENT_ORIGIN        = trimsuffix(jsondecode(base64decode(var.config_base64)).agentUrl, "/a2a")
    UI_RUNTIME_REVISION = var.image_revision
    }, var.news_enabled && var.http_api_enabled ? {
    NEWS_ORIGIN = trimsuffix(jsondecode(base64decode(var.config_base64)).newsApiUrl, "/api/v1")
    } : {}, var.news_enabled && !var.http_api_enabled ? {
    MCP_ORIGIN = trimsuffix(jsondecode(base64decode(var.config_base64)).mcpUrl, "/mcp")
  } : {}) : {}
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
resource "azurerm_user_assigned_identity" "ui" {
  count               = local.count
  name                = "id-newsloom-${var.environment_name}-ui"
  resource_group_name = var.resource_group_name
  location            = data.azurerm_container_app_environment.existing[0].location
  tags                = merge(var.tags, { azd-env-name = var.environment_name })
  lifecycle {
    prevent_destroy = true
  }
}
resource "azurerm_role_assignment" "registry" {
  count                            = local.count
  scope                            = var.registry_id
  role_definition_name             = "AcrPull"
  principal_id                     = azurerm_user_assigned_identity.ui[0].principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}
resource "azurerm_container_app" "ui" {
  count                        = local.count
  name                         = local.name
  resource_group_name          = var.resource_group_name
  container_app_environment_id = var.container_app_environment_id
  revision_mode                = "Single"
  workload_profile_name        = "Consumption"
  tags                         = merge(var.tags, { azd-env-name = var.environment_name })
  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.ui[0].id]
  }
  registry {
    server   = var.registry_endpoint
    identity = azurerm_user_assigned_identity.ui[0].id
  }
  ingress {
    external_enabled           = true
    allow_insecure_connections = false
    target_port                = 8080
    transport                  = "http"
    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }
  template {
    min_replicas = 0
    max_replicas = 1
    container {
      name   = "web"
      image  = var.image
      cpu    = 0.25
      memory = "0.5Gi"
      readiness_probe {
        transport        = "HTTP"
        port             = 8080
        path             = "/health/live"
        interval_seconds = 10
      }
      liveness_probe {
        transport = "HTTP"
        port      = 8080
        path      = "/health/live"
      }
      dynamic "env" {
        for_each = local.environment
        content {
          name  = env.key
          value = env.value
        }
      }
    }
  }
  depends_on = [azurerm_role_assignment.registry]
}
output "UI_APP_ID" {
  value = try(azurerm_container_app.ui[0].id, "")
}
output "UI_APP_NAME" {
  value = var.enabled ? local.name : ""
}
output "UI_DEPLOYED_ORIGIN" {
  value = var.enabled ? "https://${local.name}.${data.azurerm_container_app_environment.existing[0].default_domain}" : ""
}
output "UI_IDENTITY_BASE64" {
  value = var.enabled ? base64encode(jsonencode({
    id           = azurerm_user_assigned_identity.ui[0].id
    client_id    = azurerm_user_assigned_identity.ui[0].client_id
    principal_id = azurerm_user_assigned_identity.ui[0].principal_id
  })) : ""
}
