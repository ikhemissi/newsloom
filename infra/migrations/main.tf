locals {
  prefix     = "newsloom-${var.environment_name}"
  identities = jsondecode(base64decode(var.workload_identities_base64))
  workloads  = toset(["ingestion", "enrichment", "mcp", "migrations"])
  jobs = merge(
    { migrate = { workload = "migrations", command = ["migrate"] } },
    var.verification_enabled ? {
      for name in local.workloads : "verify_${name}" => { workload = name, command = ["probe", name] }
    } : {}
  )
  environment = {
    WORKLOAD_IDENTITIES               = jsonencode(local.identities)
    POSTGRES_HOST                     = var.postgres_host
    POSTGRES_DATABASE                 = var.postgres_database
    POSTGRES_ADMIN_NAME               = var.postgres_admin_name
    MODEL_ENDPOINT                    = var.model_endpoint
    MODEL_ACCOUNT_ID                  = var.model_account_id
    ENRICHMENT_DEPLOYMENT             = var.enrichment_deployment
    EMBEDDINGS_DEPLOYMENT             = var.embeddings_deployment
    SCREENING_DEPLOYMENT              = var.screening_deployment
    AZURE_CONTAINER_REGISTRY_ENDPOINT = var.registry_endpoint
  }
  tags = merge(var.tags, { azd-env-name = var.environment_name })
}

resource "azurerm_container_app_job" "operation" {
  for_each                     = local.jobs
  name                         = each.key == "migrate" ? "migrate-${trim(substr(local.prefix, 0, 24), "-")}" : "verify-${trim(substr(local.prefix, 0, 14), "-")}-${each.value.workload}"
  resource_group_name          = var.resource_group_name
  location                     = var.location
  container_app_environment_id = var.container_app_environment_id
  workload_profile_name        = "Consumption"
  replica_timeout_in_seconds   = 900
  replica_retry_limit          = 0
  tags                         = local.tags

  manual_trigger_config {
    parallelism              = 1
    replica_completion_count = 1
  }

  identity {
    type         = "UserAssigned"
    identity_ids = [local.identities[each.value.workload].id]
  }

  registry {
    server   = var.registry_endpoint
    identity = local.identities[each.value.workload].id
  }

  template {
    container {
      name   = "platform"
      image  = var.image
      cpu    = 0.25
      memory = "0.5Gi"
      args   = each.value.command

      env {
        name  = "AZURE_CLIENT_ID"
        value = local.identities[each.value.workload].client_id
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
