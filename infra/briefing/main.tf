locals {
  identity = var.enabled ? jsondecode(base64decode(var.identity_base64)) : null
  environment = {
    AZURE_CLIENT_ID                   = var.enabled ? local.identity.client_id : ""
    POSTGRES_HOST                     = var.postgres_host
    POSTGRES_DATABASE                 = var.postgres_database
    MODEL_ENDPOINT                    = var.model_endpoint
    BRIEFING_DEPLOYMENT               = var.generation_deployment
    BRIEFING_MODEL                    = var.generation_model
    BRIEFING_MODEL_VERSION            = var.generation_version
    BRIEFING_INPUT_PRICE_PER_MILLION  = var.input_price_per_million
    BRIEFING_OUTPUT_PRICE_PER_MILLION = var.output_price_per_million
    BRIEFING_PRICE_BASIS              = var.price_basis
  }
}
resource "azurerm_container_app_job" "briefing" {
  count                        = var.enabled ? 1 : 0
  name                         = "brief-${trim(substr("newsloom-${var.environment_name}", 0, 25), "-")}"
  resource_group_name          = var.resource_group_name
  location                     = var.location
  container_app_environment_id = var.container_app_environment_id
  workload_profile_name        = "Consumption"
  replica_timeout_in_seconds   = 3600
  replica_retry_limit          = 0
  tags                         = merge(var.tags, { azd-env-name = var.environment_name })
  dynamic "manual_trigger_config" {
    for_each = var.schedule_enabled ? [] : [true]
    content {
      parallelism              = 1
      replica_completion_count = 1
    }
  }
  dynamic "schedule_trigger_config" {
    for_each = var.schedule_enabled ? [true] : []
    content {
      cron_expression          = "45 7 * * *"
      parallelism              = 1
      replica_completion_count = 1
    }
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
      name   = "briefing"
      image  = var.image
      cpu    = 0.5
      memory = "1Gi"
      args   = ["run"]
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
output "BRIEFING_JOB_ID" {
  value = var.enabled ? azurerm_container_app_job.briefing[0].id : ""
}
