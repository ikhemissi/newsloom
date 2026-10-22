locals {
  prefix = "newsloom-${var.environment_name}"
  suffix = substr(sha256("${var.subscription_id}/${var.environment_name}"), 0, 8)
  tags = merge(var.tags, {
    azd-env-name = var.environment_name
  })
  workloads = toset(["ingestion", "enrichment", "mcp", "migrations"])
  workload_identities = {
    for name, identity in azurerm_user_assigned_identity.workload : name => {
      id           = identity.id
      client_id    = identity.client_id
      principal_id = identity.principal_id
    }
  }
  inference_actions = {
    ingestion = ["Microsoft.CognitiveServices/accounts/AIServices/providers/action"]
    enrichment = [
      "Microsoft.CognitiveServices/accounts/OpenAI/deployments/chat/completions/action",
      "Microsoft.CognitiveServices/accounts/OpenAI/deployments/embeddings/action",
    ]
    mcp = ["Microsoft.CognitiveServices/accounts/OpenAI/deployments/embeddings/action"]
  }
}

data "azurerm_client_config" "current" {}

resource "azurerm_resource_group" "application" {
  name     = var.resource_group_name
  location = var.location
  tags     = local.tags

  lifecycle {
    prevent_destroy = true
  }
}

resource "azurerm_container_registry" "application" {
  name                = "acr${replace(local.prefix, "-", "")}${local.suffix}"
  resource_group_name = azurerm_resource_group.application.name
  location            = var.location
  sku                 = "Basic"
  admin_enabled       = false
  tags                = local.tags

  lifecycle {
    prevent_destroy = true
  }
}

resource "azurerm_log_analytics_workspace" "application" {
  name                         = "log-${local.prefix}"
  resource_group_name          = azurerm_resource_group.application.name
  location                     = var.location
  sku                          = "PerGB2018"
  retention_in_days            = var.log_retention_days
  daily_quota_gb               = var.log_daily_cap_gb
  local_authentication_enabled = false
  tags                         = local.tags
}

resource "azurerm_application_insights" "application" {
  name                         = "appi-${local.prefix}"
  resource_group_name          = azurerm_resource_group.application.name
  location                     = var.location
  workspace_id                 = azurerm_log_analytics_workspace.application.id
  application_type             = "other"
  local_authentication_enabled = false
  daily_data_cap_in_gb         = var.log_daily_cap_gb
  retention_in_days            = var.log_retention_days
  tags                         = local.tags
}

resource "azurerm_container_app_environment" "application" {
  name                = "cae-${local.prefix}"
  resource_group_name = azurerm_resource_group.application.name
  location            = var.location
  logs_destination    = "azure-monitor"
  tags                = local.tags

  workload_profile {
    name                  = "Consumption"
    workload_profile_type = "Consumption"
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "azurerm_monitor_diagnostic_setting" "containers" {
  name                       = "platform-logs"
  target_resource_id         = azurerm_container_app_environment.application.id
  log_analytics_workspace_id = azurerm_log_analytics_workspace.application.id

  enabled_log {
    category_group = "allLogs"
  }
}

resource "azurerm_user_assigned_identity" "workload" {
  for_each            = local.workloads
  name                = "id-${local.prefix}-${each.key}"
  resource_group_name = azurerm_resource_group.application.name
  location            = var.location
  tags                = local.tags
}

resource "azurerm_role_assignment" "registry_pull" {
  for_each                         = local.workloads
  scope                            = azurerm_container_registry.application.id
  role_definition_name             = "AcrPull"
  principal_id                     = azurerm_user_assigned_identity.workload[each.key].principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}

resource "azurerm_role_assignment" "telemetry" {
  for_each                         = local.inference_actions
  scope                            = azurerm_application_insights.application.id
  role_definition_name             = "Monitoring Metrics Publisher"
  principal_id                     = azurerm_user_assigned_identity.workload[each.key].principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}

resource "azurerm_postgresql_flexible_server" "application" {
  name                          = "psql-${local.prefix}-${local.suffix}"
  resource_group_name           = azurerm_resource_group.application.name
  location                      = var.location
  version                       = "18"
  sku_name                      = var.postgres_sku
  storage_mb                    = var.postgres_storage_mb
  storage_tier                  = "P4"
  auto_grow_enabled             = false
  backup_retention_days         = var.postgres_backup_days
  geo_redundant_backup_enabled  = false
  public_network_access_enabled = true
  tags                          = local.tags

  authentication {
    active_directory_auth_enabled = true
    password_auth_enabled         = false
    tenant_id                     = data.azurerm_client_config.current.tenant_id
  }

  lifecycle {
    prevent_destroy = true
    # Preserve Azure's automatically selected availability zone.
    ignore_changes = [zone]
  }
}

resource "azurerm_postgresql_flexible_server_database" "application" {
  name      = "newsloom"
  server_id = azurerm_postgresql_flexible_server.application.id
  charset   = "UTF8"
  collation = "en_US.utf8"

  # Azure rejects concurrent mutations of the same PostgreSQL server.
  depends_on = [azurerm_postgresql_flexible_server_configuration.extensions]

  lifecycle {
    prevent_destroy = true
  }
}

resource "azurerm_postgresql_flexible_server_firewall_rule" "azure_services" {
  name             = "AllowAzureServices"
  server_id        = azurerm_postgresql_flexible_server.application.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"

  depends_on = [azurerm_postgresql_flexible_server_database.application]
}

resource "azurerm_postgresql_flexible_server_configuration" "extensions" {
  name      = "azure.extensions"
  server_id = azurerm_postgresql_flexible_server.application.id
  value     = "VECTOR"

  depends_on = [azurerm_postgresql_flexible_server_active_directory_administrator.migrations]
}

resource "azurerm_postgresql_flexible_server_active_directory_administrator" "migrations" {
  server_name         = azurerm_postgresql_flexible_server.application.name
  resource_group_name = azurerm_resource_group.application.name
  tenant_id           = data.azurerm_client_config.current.tenant_id
  object_id           = azurerm_user_assigned_identity.workload["migrations"].principal_id
  principal_name      = azurerm_user_assigned_identity.workload["migrations"].name
  principal_type      = "ServicePrincipal"
}

resource "azurerm_cognitive_account" "models" {
  name                  = "ai-${local.prefix}-${local.suffix}"
  resource_group_name   = azurerm_resource_group.application.name
  location              = var.location
  kind                  = "AIServices"
  sku_name              = "S0"
  custom_subdomain_name = "ai-${local.prefix}-${local.suffix}"
  local_auth_enabled    = false
  tags                  = local.tags

  lifecycle {
    prevent_destroy = true
  }
}

resource "azurerm_cognitive_deployment" "model" {
  for_each               = var.models
  name                   = each.value.deployment_name
  cognitive_account_id   = azurerm_cognitive_account.models.id
  version_upgrade_option = "NoAutoUpgrade"

  model {
    format  = each.value.format
    name    = each.value.name
    version = each.value.version
  }

  sku {
    name     = each.value.sku
    capacity = each.value.capacity
  }
}

resource "azurerm_role_definition" "inference" {
  for_each          = local.inference_actions
  name              = "${local.prefix}-${each.key}-inference"
  scope             = azurerm_resource_group.application.id
  description       = "Newsloom ${each.key}: only its configured inference API operations."
  assignable_scopes = [azurerm_resource_group.application.id]

  permissions {
    actions      = []
    data_actions = each.value
  }
}

resource "azurerm_role_assignment" "inference" {
  for_each                         = local.inference_actions
  scope                            = azurerm_cognitive_account.models.id
  role_definition_id               = azurerm_role_definition.inference[each.key].role_definition_resource_id
  principal_id                     = azurerm_user_assigned_identity.workload[each.key].principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}
