locals {
  count  = var.enabled ? 1 : 0
  prefix = "newsloom-${var.environment_name}"
  group  = "/subscriptions/${var.subscription_id}/resourceGroups/${var.resource_group_name}"
}

# Used only by the CI live-eval step (GitHub OIDC, no secret).
resource "azurerm_user_assigned_identity" "eval" {
  count               = local.count
  name                = "id-${local.prefix}-ci-eval"
  resource_group_name = var.resource_group_name
  location            = var.location
  tags                = merge(var.tags, { azd-env-name = var.environment_name })
}

resource "azurerm_federated_identity_credential" "github" {
  for_each                  = var.enabled ? { for s in var.github_subjects : (endswith(s, ":pull_request") ? "pull-request" : "main") => s } : {}
  name                      = "github-ci-eval-${each.key}"
  user_assigned_identity_id = azurerm_user_assigned_identity.eval[0].id
  issuer                    = "https://token.actions.githubusercontent.com"
  audience                  = ["api://AzureADTokenExchange"]
  subject                   = each.value
}

# Azure OpenAI data-plane roles cannot be scoped to one deployment.
resource "azurerm_role_definition" "chat" {
  count             = local.count
  name              = "${local.prefix}-ci-eval-chat"
  scope             = local.group
  description       = "CI live evals: chat completions only; no embeddings or management operations."
  assignable_scopes = [local.group]
  permissions {
    actions      = []
    data_actions = ["Microsoft.CognitiveServices/accounts/OpenAI/deployments/chat/completions/action"]
  }
}

resource "azurerm_role_assignment" "chat" {
  count                            = local.count
  scope                            = var.model_account_id
  role_definition_id               = azurerm_role_definition.chat[0].role_definition_resource_id
  principal_id                     = azurerm_user_assigned_identity.eval[0].principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}

output "EVAL_IDENTITY_CLIENT_ID" {
  value = var.enabled ? azurerm_user_assigned_identity.eval[0].client_id : ""
}
