output "AZURE_LOCATION" {
  description = "Core location available to azd hooks."
  value       = var.location
}

output "AZURE_RESOURCE_GROUP" {
  value = azurerm_resource_group.application.name
}

output "AZURE_CONTAINER_REGISTRY_NAME" {
  value = azurerm_container_registry.application.name
}

output "AZURE_CONTAINER_REGISTRY_ENDPOINT" {
  value = azurerm_container_registry.application.login_server
}

output "AZURE_CONTAINER_REGISTRY_ID" {
  value = azurerm_container_registry.application.id
}

output "AZURE_CONTAINER_APPS_ENVIRONMENT_ID" {
  value = azurerm_container_app_environment.application.id
}

output "POSTGRES_HOST" {
  value = azurerm_postgresql_flexible_server.application.fqdn
}

output "POSTGRES_DATABASE" {
  value = azurerm_postgresql_flexible_server_database.application.name
}

output "POSTGRES_SERVER_NAME" {
  value = azurerm_postgresql_flexible_server.application.name
}

output "POSTGRES_ADMIN_NAME" {
  value = azurerm_user_assigned_identity.workload["migrations"].name
}

output "WORKLOAD_IDENTITIES" {
  value = jsonencode(local.workload_identities)
}

output "WORKLOAD_IDENTITIES_BASE64" {
  description = "JSON transport for azd's string substitution into migration inputs; not encryption."
  value       = base64encode(jsonencode(local.workload_identities))
}

output "MODEL_ENDPOINT" {
  description = "Foundry provider endpoint, distinct from the generic Cognitive Services endpoint."
  value       = "https://${azurerm_cognitive_account.models.custom_subdomain_name}.services.ai.azure.com/"
}

output "MODEL_ACCOUNT_NAME" {
  value = azurerm_cognitive_account.models.name
}

output "MODEL_ACCOUNT_ID" {
  value = azurerm_cognitive_account.models.id
}

output "MODEL_PROJECT_MANAGEMENT_ENABLED" {
  description = "Lasting parent prerequisite; never disable it to retire evaluation assets."
  value       = azurerm_cognitive_account.models.project_management_enabled
}

output "MODEL_ACCOUNT_IDENTITY_PRINCIPAL_ID" {
  description = "Required account identity; no evaluation or production roles are assigned to it."
  value       = azurerm_cognitive_account.models.identity[0].principal_id
}

output "MODEL_ACCOUNT_IDENTITY_TENANT_ID" {
  value = azurerm_cognitive_account.models.identity[0].tenant_id
}

output "APPLICATIONINSIGHTS_CONNECTION_STRING" {
  value     = azurerm_application_insights.application.connection_string
  sensitive = true
}

output "APPLICATIONINSIGHTS_ID" {
  value = azurerm_application_insights.application.id
}

output "LOG_ANALYTICS_WORKSPACE_ID" {
  value = azurerm_log_analytics_workspace.application.workspace_id
}

output "WORKLOAD_GRANTS" {
  value = jsonencode({
    for name in local.workloads : name => {
      principal_id = azurerm_user_assigned_identity.workload[name].principal_id
      registry     = { scope = azurerm_container_registry.application.id, role = "AcrPull" }
      inference = contains(keys(local.inference_actions), name) ? {
        scope = azurerm_cognitive_account.models.id, data_actions = local.inference_actions[name]
      } : null
      telemetry = contains(keys(local.inference_actions), name) ? {
        scope = azurerm_application_insights.application.id, role = "Monitoring Metrics Publisher"
      } : null
      database = {
        name = azurerm_postgresql_flexible_server_database.application.name
        role = name == "migrations" ? "administrator" : "login-only"
      }
    }
  })
}
