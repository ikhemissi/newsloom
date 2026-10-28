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
