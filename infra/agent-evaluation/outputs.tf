output "AGENT_EVALUATION_PROJECT_ID" {
  value = var.enabled ? azurerm_cognitive_account_project.evaluation[0].id : ""
}

output "AGENT_EVALUATION_PROJECT_ENDPOINT" {
  description = "Expected native project route; deployed endpoint-map readback must confirm it before pilot use."
  value       = var.enabled ? "${trimsuffix(var.model_endpoint, "/")}/api/projects/${local.name}" : ""
}

output "AGENT_EVALUATION_PROJECT_ENDPOINTS_BASE64" {
  description = "Native endpoint map for independent post-provisioning verification."
  value       = var.enabled ? base64encode(jsonencode(azurerm_cognitive_account_project.evaluation[0].endpoints)) : ""
}

output "AGENT_EVALUATION_PROJECT_PRINCIPAL_ID" {
  value = var.enabled ? azurerm_cognitive_account_project.evaluation[0].identity[0].principal_id : ""
}

output "AGENT_EVALUATION_GRANTS_BASE64" {
  description = "Exact proposed operator scope/operation inventory, not proof of working API authorization."
  value       = var.enabled ? base64encode(jsonencode(local.grants)) : ""
}

output "AGENT_EVALUATION_FOUNDRY_USER_ASSIGNMENT_BASE64" {
  description = "Separately approved project/operator assignment; not proof of working catalog authorization."
  value = length(azurerm_role_assignment.foundry_user) == 1 ? base64encode(jsonencode({
    id                 = azurerm_role_assignment.foundry_user[0].id
    principal_id       = azurerm_role_assignment.foundry_user[0].principal_id
    principal_type     = azurerm_role_assignment.foundry_user[0].principal_type
    role_definition_id = azurerm_role_assignment.foundry_user[0].role_definition_id
    scope              = azurerm_role_assignment.foundry_user[0].scope
  })) : ""
}

output "AGENT_EVALUATION_FOUNDRY_PROJECT_MANAGER_ASSIGNMENT_BASE64" {
  description = "Separately approved project/operator assignment; not proof of working evaluation authorization."
  value = length(azurerm_role_assignment.foundry_project_manager) == 1 ? base64encode(jsonencode({
    id                 = azurerm_role_assignment.foundry_project_manager[0].id
    principal_id       = azurerm_role_assignment.foundry_project_manager[0].principal_id
    principal_type     = azurerm_role_assignment.foundry_project_manager[0].principal_type
    role_definition_id = azurerm_role_assignment.foundry_project_manager[0].role_definition_id
    scope              = azurerm_role_assignment.foundry_project_manager[0].scope
  })) : ""
}

output "AGENT_EVALUATION_STORAGE_ACCOUNT_ID" {
  value = local.data_enabled ? azapi_resource.evaluation_storage[0].id : ""
}

output "AGENT_EVALUATION_STORAGE_CONNECTION_ID" {
  value = local.data_enabled ? azapi_resource.evaluation_storage_connection[0].id : ""
}

output "AGENT_EVALUATION_DATA_GRANTS_BASE64" {
  value = local.data_enabled ? base64encode(jsonencode({
    for key, grant in local.data_grants : key => {
      id                 = azapi_resource.data_grants[key].id
      principal_id       = grant.principal_id
      principal_type     = grant.principal_type
      scope              = grant.parent_id
      role_definition_id = "/subscriptions/${var.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/${grant.role_id}"
    }
  })) : ""
}
