locals {
  identity = jsondecode(base64decode(var.workload_identities_base64)).ingestion
  environment = {
    AZURE_CLIENT_ID        = local.identity.client_id
    POSTGRES_HOST          = var.postgres_host
    POSTGRES_DATABASE      = var.postgres_database
    MODEL_ENDPOINT         = var.model_endpoint
    SCREENING_DEPLOYMENT   = var.screening_deployment
    SCREENING_MODEL        = "Microsoft-Decision-1"
    SCREENING_VERSION      = "1"
    SCANNER_THRESHOLD      = var.screening_threshold
    SCANNER_CALIBRATION_ID = var.screening_calibration_id
  }
}

resource "azurerm_container_app_job" "ingestion" {
  name                         = "ingest-${trim(substr("newsloom-${var.environment_name}", 0, 25), "-")}"
  resource_group_name          = var.resource_group_name
  location                     = var.location
  container_app_environment_id = var.container_app_environment_id
  workload_profile_name        = "Consumption"
  replica_timeout_in_seconds   = 900
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
      cron_expression          = "*/30 * * * *"
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
      name   = "ingestion"
      image  = var.image
      cpu    = 0.25
      memory = "0.5Gi"
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
  lifecycle {
    precondition {
      condition     = !var.schedule_enabled || (var.screening_threshold != "" && var.screening_calibration_id != "")
      error_message = "Scheduling requires the measured threshold and matching policy calibration."
    }
  }
}

output "INGESTION_JOB_ID" {
  value = azurerm_container_app_job.ingestion.id
}
