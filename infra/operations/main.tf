locals {
  identity = jsondecode(base64decode(var.identity_base64))
  group    = "/subscriptions/${var.subscription_id}/resourceGroups/${var.resource_group_name}"
  short    = trim(substr("newsloom-${var.environment_name}", 0, 24), "-")
  # UTC: 23:00 is midnight in Paris in winter, 01:00 in summer.
  jobs = {
    nightly = { command = "nightly", cron = "0 23 * * *", timeout = 3600 }
    wake    = { command = "wake", cron = "0 7 * * *", timeout = 1800 }
    backup  = { command = "backup", cron = "", timeout = 3600 }
  }
  environment = {
    AZURE_CLIENT_ID         = local.identity.client_id
    POSTGRES_HOST           = var.postgres_host
    POSTGRES_DATABASE       = var.postgres_database
    POSTGRES_SERVER_ID      = "${local.group}/providers/Microsoft.DBforPostgreSQL/flexibleServers/${var.postgres_server_name}"
    AZURE_RESOURCE_GROUP_ID = local.group
    BACKUP_ACCOUNT_URL      = var.backup_account_url
    BACKUP_CONTAINER        = var.backup_container
  }
}

resource "azurerm_container_app_job" "operations" {
  for_each                     = local.jobs
  name                         = "${each.key}-${local.short}"
  resource_group_name          = var.resource_group_name
  location                     = var.location
  container_app_environment_id = var.container_app_environment_id
  workload_profile_name        = "Consumption"
  replica_timeout_in_seconds   = each.value.timeout
  replica_retry_limit          = 0
  tags                         = merge(var.tags, { azd-env-name = var.environment_name })
  dynamic "manual_trigger_config" {
    for_each = var.schedule_enabled && each.value.cron != "" ? [] : [true]
    content {
      parallelism              = 1
      replica_completion_count = 1
    }
  }
  dynamic "schedule_trigger_config" {
    for_each = var.schedule_enabled && each.value.cron != "" ? [true] : []
    content {
      cron_expression          = each.value.cron
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
      name   = "operations"
      image  = var.image
      cpu    = 0.5
      memory = "1Gi"
      args   = [each.value.command]
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
output "OPERATIONS_NIGHTLY_JOB_NAME" {
  value = azurerm_container_app_job.operations["nightly"].name
}
output "OPERATIONS_BACKUP_JOB_NAME" {
  value = azurerm_container_app_job.operations["backup"].name
}
output "OPERATIONS_WAKE_JOB_NAME" {
  value = azurerm_container_app_job.operations["wake"].name
}
