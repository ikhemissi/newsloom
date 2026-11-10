locals {
  count = var.enabled ? 1 : 0
  name  = "research-newsloom-${var.environment_name}"
  agent = var.enabled ? jsondecode(base64decode(var.agent_identity_base64)) : null
}

# A dedicated project: anyone with access to a project can read keys stored in its
# connections, so only the agent and the operator use this one.
resource "azurerm_cognitive_account_project" "research" {
  count                = local.count
  name                 = local.name
  cognitive_account_id = var.model_account_id
  location             = var.location
  display_name         = "Newsloom web research"
  description          = "Holds the Web IQ connection used by the research agent."
  tags                 = merge(var.tags, { azd-env-name = var.environment_name, newsloom-slice = "web-research" })

  identity {
    type = "SystemAssigned"
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "azurerm_role_assignment" "agent" {
  count                            = local.count
  scope                            = azurerm_cognitive_account_project.research[0].id
  role_definition_id               = "/subscriptions/${var.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/${var.foundry_user_role_id}"
  principal_id                     = local.agent.principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
  lifecycle {
    precondition {
      condition     = var.foundry_user_role_id != ""
      error_message = "Web research needs the Foundry User role ID."
    }
  }
}

output "WEB_RESEARCH_PROJECT_ID" {
  value = var.enabled ? azurerm_cognitive_account_project.research[0].id : ""
}
output "WEB_RESEARCH_PROJECT_ENDPOINT" {
  value = var.enabled ? "https://${basename(var.model_account_id)}.services.ai.azure.com/api/projects/${local.name}" : ""
}
