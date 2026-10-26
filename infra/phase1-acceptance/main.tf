locals {
  count  = var.enabled ? 1 : 0
  prefix = "newsloom-${var.environment_name}"
  group  = "/subscriptions/${var.subscription_id}/resourceGroups/${var.resource_group_name}"
  tags   = merge(var.tags, { azd-env-name = var.environment_name })
  configuration = var.enabled ? base64encode(jsonencode(merge(var.test_settings, {
    principal_id   = azurerm_user_assigned_identity.acceptance[0].principal_id
    client_id      = azurerm_user_assigned_identity.acceptance[0].client_id
    image_revision = var.image_revision
  }))) : ""
}

data "azurerm_log_analytics_workspace" "application" {
  count               = local.count
  name                = "log-${local.prefix}"
  resource_group_name = var.resource_group_name
}

data "azurerm_container_app_environment" "application" {
  count               = local.count
  name                = "cae-${local.prefix}"
  resource_group_name = var.resource_group_name
  lifecycle {
    postcondition {
      condition     = lower(self.id) == lower(var.container_app_environment_id)
      error_message = "Log metadata must come from the existing owning environment."
    }
  }
}

resource "azurerm_user_assigned_identity" "acceptance" {
  count               = local.count
  name                = "phase1-${local.prefix}"
  resource_group_name = var.resource_group_name
  location            = var.location
  tags                = local.tags
  lifecycle {
    prevent_destroy = true
  }
}
resource "azurerm_federated_identity_credential" "github" {
  count                     = local.count
  name                      = "github-phase1-acceptance"
  user_assigned_identity_id = azurerm_user_assigned_identity.acceptance[0].id
  issuer                    = "https://token.actions.githubusercontent.com"
  audience                  = ["api://AzureADTokenExchange"]
  subject                   = var.github_subject
}
resource "azurerm_role_definition" "inference" {
  count             = local.count
  name              = "${local.prefix}-phase1-inference"
  scope             = local.group
  assignable_scopes = [local.group]
  description       = "Isolated phase acceptance: only the three existing inference API operations."
  permissions {
    actions = []
    data_actions = [
      "Microsoft.CognitiveServices/accounts/AIServices/providers/action",
      "Microsoft.CognitiveServices/accounts/OpenAI/deployments/chat/completions/action",
      "Microsoft.CognitiveServices/accounts/OpenAI/deployments/embeddings/action",
    ]
  }
}
resource "azurerm_role_assignment" "inference" {
  count                            = local.count
  scope                            = var.model_account_id
  role_definition_id               = azurerm_role_definition.inference[0].role_definition_resource_id
  principal_id                     = azurerm_user_assigned_identity.acceptance[0].principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}
resource "azurerm_role_assignment" "registry" {
  count                            = local.count
  scope                            = var.registry_id
  role_definition_name             = "AcrPull"
  principal_id                     = azurerm_user_assigned_identity.acceptance[0].principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}
resource "azurerm_role_assignment" "telemetry" {
  count                            = local.count
  scope                            = var.applicationinsights_id
  role_definition_name             = "Monitoring Metrics Publisher"
  principal_id                     = azurerm_user_assigned_identity.acceptance[0].principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}
resource "azurerm_container_app_job" "acceptance" {
  count                        = local.count
  name                         = "accept-${local.prefix}"
  resource_group_name          = var.resource_group_name
  location                     = var.location
  container_app_environment_id = var.container_app_environment_id
  workload_profile_name        = "Consumption"
  replica_timeout_in_seconds   = 1200
  replica_retry_limit          = 0
  tags                         = local.tags
  manual_trigger_config {
    parallelism              = 1
    replica_completion_count = 1
  }
  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.acceptance[0].id]
  }
  registry {
    server   = var.registry_endpoint
    identity = azurerm_user_assigned_identity.acceptance[0].id
  }
  template {
    container {
      name   = "acceptance"
      image  = var.image
      cpu    = 0.25
      memory = "0.5Gi"
      args   = ["run"]
      env {
        name  = "PHASE1_CONFIG_BASE64"
        value = local.configuration
      }
      env {
        name  = "APPLICATIONINSIGHTS_CONNECTION_STRING"
        value = var.applicationinsights_connection_string
      }
    }
  }
  depends_on = [azurerm_role_assignment.registry, azurerm_role_assignment.inference]
}
resource "azurerm_role_definition" "control" {
  count             = local.count
  name              = "${local.prefix}-phase1-job-control"
  scope             = local.group
  assignable_scopes = [local.group]
  description       = "Read/start/stop and execution status for only the acceptance job."
  permissions {
    actions = [
      "Microsoft.App/jobs/read",
      "Microsoft.App/jobs/start/action",
      "Microsoft.App/jobs/stop/action",
      "Microsoft.App/jobs/execution/read",
      "Microsoft.App/jobs/executions/read",
    ]
    data_actions = []
  }
}
resource "azurerm_role_assignment" "control" {
  count                            = local.count
  scope                            = azurerm_container_app_job.acceptance[0].id
  role_definition_id               = azurerm_role_definition.control[0].role_definition_resource_id
  principal_id                     = azurerm_user_assigned_identity.acceptance[0].principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}
resource "azurerm_role_assignment" "log_reader" {
  count                            = local.count
  scope                            = data.azurerm_log_analytics_workspace.application[0].id
  role_definition_name             = "Log Analytics Data Reader"
  principal_id                     = azurerm_user_assigned_identity.acceptance[0].principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
  condition_version                = "2.0"
  condition                        = <<-EOT
    (
      !(ActionMatches{'Microsoft.OperationalInsights/workspaces/tables/data/read'})
      OR
      (
        @Resource[Microsoft.OperationalInsights/workspaces/tables:name] StringEquals 'ContainerAppConsoleLogs'
        AND
        @Resource[Microsoft.OperationalInsights/workspaces/tables/record:JobName<$key_case_sensitive$>] StringEquals 'accept-${local.prefix}'
        AND
        @Resource[Microsoft.OperationalInsights/workspaces/tables/record:EnvironmentName<$key_case_sensitive$>] StringEquals '${split(".", data.azurerm_container_app_environment.application[0].default_domain)[0]}'
      )
    )
  EOT
}
output "PHASE1_CLIENT_ID" {
  value = var.enabled ? azurerm_user_assigned_identity.acceptance[0].client_id : ""
}
output "PHASE1_PRINCIPAL_ID" {
  value = var.enabled ? azurerm_user_assigned_identity.acceptance[0].principal_id : ""
}
output "PHASE1_JOB_ID" {
  value = var.enabled ? azurerm_container_app_job.acceptance[0].id : ""
}
