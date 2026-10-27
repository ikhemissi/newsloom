locals {
  count = var.enabled ? 1 : 0
  name  = "agent-${trim(substr("newsloom-${var.environment_name}", 0, 23), "-")}"
  identity = var.enabled ? jsondecode(base64decode(var.identity_base64)) : {
    id = "", client_id = "", principal_id = ""
  }
  resource_url = var.enabled ? "https://${local.name}.${data.azurerm_container_app_environment.existing[0].default_domain}/a2a" : ""
  environment = {
    AZURE_CLIENT_ID        = local.identity.client_id
    AGENT_TENANT_ID        = var.tenant_id
    AGENT_API_CLIENT_ID    = var.api_client_id
    AGENT_RESOURCE_URL     = local.resource_url
    AGENT_ALLOWED_ORIGINS  = join(",", sort(tolist(var.allowed_origins)))
    AGENT_RUNTIME_REVISION = var.image_revision
    MCP_API_CLIENT_ID      = var.mcp_api_client_id
    MCP_RESOURCE_URL       = var.mcp_resource_url
    MODEL_ENDPOINT         = var.model_endpoint
    AGENT_CHAT_DEPLOYMENT  = var.chat_deployment
  }
}
data "azurerm_container_app_environment" "existing" {
  count               = local.count
  name                = basename(var.container_app_environment_id)
  resource_group_name = var.resource_group_name
  lifecycle {
    postcondition {
      condition     = self.id == var.container_app_environment_id
      error_message = "Use the retained owning Container Apps environment, not a lookalike."
    }
  }
}
resource "azurerm_container_app" "agent" {
  count                        = local.count
  name                         = local.name
  resource_group_name          = var.resource_group_name
  container_app_environment_id = var.container_app_environment_id
  revision_mode                = "Single"
  workload_profile_name        = "Consumption"
  tags                         = merge(var.tags, { azd-env-name = var.environment_name })
  identity {
    type         = "UserAssigned"
    identity_ids = [local.identity.id]
  }
  registry {
    server   = var.registry_endpoint
    identity = local.identity.id
  }
  ingress {
    external_enabled           = true
    target_port                = 8000
    transport                  = "http"
    allow_insecure_connections = false
    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }
  template {
    min_replicas = 1
    max_replicas = 1
    container {
      name   = "agent"
      image  = var.image
      cpu    = 0.25
      memory = "0.5Gi"
      startup_probe {
        transport               = "HTTP"
        port                    = 8000
        path                    = "/health/live"
        initial_delay           = 5
        interval_seconds        = 5
        failure_count_threshold = 20
        timeout                 = 2
      }
      liveness_probe {
        transport               = "HTTP"
        port                    = 8000
        path                    = "/health/live"
        interval_seconds        = 30
        failure_count_threshold = 3
        timeout                 = 2
      }
      readiness_probe {
        transport               = "HTTP"
        port                    = 8000
        path                    = "/health/live"
        interval_seconds        = 30
        failure_count_threshold = 3
        timeout                 = 2
      }
      dynamic "env" {
        for_each = local.environment
        content {
          name  = env.key
          value = env.value
        }
      }
      env {
        name  = "APPLICATIONINSIGHTS_CONNECTION_STRING"
        value = var.applicationinsights_connection_string
      }
    }
  }
  lifecycle {
    precondition {
      condition     = var.api_client_id != var.mcp_api_client_id && var.api_client_id != local.identity.client_id
      error_message = "Agent, MCP and managed-identity client IDs must remain separate."
    }
  }
}
output "AGENT_APP_ID" {
  value = try(azurerm_container_app.agent[0].id, "")
}
output "AGENT_APP_NAME" {
  value = var.enabled ? local.name : ""
}
output "AGENT_RESOURCE_URL" {
  value = local.resource_url
}
