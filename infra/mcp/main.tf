data "azurerm_container_app_environment" "existing" {
  name                = basename(var.container_app_environment_id)
  resource_group_name = var.resource_group_name
}
locals {
  name            = "mcp-${trim(substr("newsloom-${var.environment_name}", 0, 25), "-")}"
  identity        = jsondecode(base64decode(var.workload_identities_base64)).mcp
  host            = "${local.name}.${data.azurerm_container_app_environment.existing.default_domain}"
  resource_url    = "https://${local.host}/mcp"
  browser_origins = var.allowed_origins_base64 == "" ? var.allowed_origins : toset(jsondecode(base64decode(var.allowed_origins_base64)))
  environment = merge(var.snapshot_url == "" ? {} : { SNAPSHOT_URL = var.snapshot_url }, {
    NEWS_API_ENABLED             = tostring(var.news_api_enabled)
    NEWS_BRIEFING_ENABLED        = tostring(var.news_briefing_enabled)
    FEEDBACK_REVIEWER_OBJECT_IDS = var.feedback_reviewer_object_ids
    AZURE_CLIENT_ID              = local.identity.client_id
    MCP_TENANT_ID                = var.tenant_id
    MCP_API_CLIENT_ID            = var.api_client_id
    MCP_RESOURCE_URL             = local.resource_url
    MCP_ALLOWED_ORIGINS          = join(",", sort(tolist(local.browser_origins)))
    POSTGRES_HOST                = var.postgres_host
    POSTGRES_DATABASE            = var.postgres_database
    MODEL_ENDPOINT               = var.model_endpoint
    EMBEDDINGS_DEPLOYMENT        = var.embedding_deployment
    EMBEDDINGS_MODEL             = var.embedding_model
    EMBEDDINGS_VERSION           = var.embedding_version
  })
}

# Writes the read snapshot after the last ingestion run and before the 23:00 UTC stop.
resource "azurerm_container_app_job" "snapshot" {
  count                        = var.snapshot_url == "" ? 0 : 1
  name                         = "snapshot-${trim(substr("newsloom-${var.environment_name}", 0, 23), "-")}"
  resource_group_name          = var.resource_group_name
  location                     = var.location
  container_app_environment_id = var.container_app_environment_id
  workload_profile_name        = "Consumption"
  replica_timeout_in_seconds   = 600
  replica_retry_limit          = 1
  tags                         = merge(var.tags, { azd-env-name = var.environment_name })
  schedule_trigger_config {
    cron_expression          = "45 22 * * *"
    parallelism              = 1
    replica_completion_count = 1
  }
  identity {
    type         = "UserAssigned"
    identity_ids = [local.identity.id]
  }
  registry {
    server   = var.registry_endpoint
    identity = local.identity.id
  }
  template {
    container {
      name   = "snapshot"
      image  = var.image
      cpu    = 0.5
      memory = "1Gi"
      args   = ["snapshot"]
      env {
        name  = "APPLICATIONINSIGHTS_CONNECTION_STRING"
        value = var.applicationinsights_connection_string
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
}

resource "azurerm_container_app" "mcp" {
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
      name   = "mcp"
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
        path                    = "/health/ready"
        interval_seconds        = 30
        failure_count_threshold = 3
        timeout                 = 6
      }
      env {
        name  = "APPLICATIONINSIGHTS_CONNECTION_STRING"
        value = var.applicationinsights_connection_string
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
}

output "MCP_APP_ID" {
  value = azurerm_container_app.mcp.id
}
output "MCP_APP_NAME" {
  value = azurerm_container_app.mcp.name
}
output "MCP_RESOURCE_URL" {
  value = local.resource_url
}
output "SNAPSHOT_JOB_NAME" {
  value = var.snapshot_url == "" ? "" : azurerm_container_app_job.snapshot[0].name
}
