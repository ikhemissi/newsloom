locals {
  prefix   = "newsloom-${var.environment_name}-agent-evaluation"
  name     = "eval-newsloom-${var.environment_name}"
  group_id = "/subscriptions/${var.subscription_id}/resourceGroups/${var.resource_group_name}"
  permission_sets = {
    chat = ["Microsoft.CognitiveServices/accounts/OpenAI/deployments/chat/completions/action"]
    evaluations = [
      "Microsoft.CognitiveServices/accounts/AIServices/evaluations/read",
      "Microsoft.CognitiveServices/accounts/AIServices/evaluations/write",
      "Microsoft.CognitiveServices/accounts/AIServices/evaluations/delete",
      "Microsoft.CognitiveServices/accounts/OpenAI/evals/read",
      "Microsoft.CognitiveServices/accounts/OpenAI/evals/write",
    ]
  }
  grants = var.enabled ? {
    for name, role in azurerm_role_definition.operator : name => {
      principal_id       = var.operator_principal_id
      principal_type     = "User"
      scope              = azurerm_role_assignment.operator[name].scope
      role_definition_id = role.role_definition_resource_id
      actions            = role.permissions[0].actions
      data_actions       = role.permissions[0].data_actions
      not_actions        = role.permissions[0].not_actions
      not_data_actions   = role.permissions[0].not_data_actions
    }
  } : {}
}

data "azurerm_client_config" "current" {
  count = var.enabled ? 1 : 0
  lifecycle {
    postcondition {
      condition = (
        self.subscription_id == var.subscription_id &&
        self.tenant_id == var.tenant_id &&
        self.object_id == var.operator_principal_id
      )
      error_message = "The provider must use the exact retained subscription, tenant and reviewed operator."
    }
  }
}

resource "azurerm_cognitive_account_project" "evaluation" {
  count                = var.enabled ? 1 : 0
  name                 = local.name
  cognitive_account_id = var.model_account_id
  location             = var.location
  display_name         = "Newsloom agent evaluation"
  description          = "Synthetic evaluation interoperability foundation; not production content or an agent runtime."
  tags                 = merge(var.tags, { azd-env-name = var.environment_name, newsloom-slice = "agent-evaluation" })

  identity {
    type = "SystemAssigned"
  }

  lifecycle {
    prevent_destroy = true
    postcondition {
      condition = (
        self.identity[0].tenant_id == var.tenant_id &&
        self.identity[0].principal_id != var.operator_principal_id
      )
      error_message = "The project must have its own managed identity in the retained tenant."
    }
  }
  depends_on = [data.azurerm_client_config.current]
}

resource "azurerm_role_definition" "operator" {
  for_each          = var.enabled ? local.permission_sets : {}
  name              = "${local.prefix}-${each.key}"
  scope             = local.group_id
  description       = "Newsloom evaluation operator: explicit ${each.key} data operations only."
  assignable_scopes = [local.group_id]

  permissions {
    actions          = []
    not_actions      = []
    data_actions     = each.value
    not_data_actions = []
  }
  depends_on = [data.azurerm_client_config.current]
}

resource "azurerm_role_assignment" "operator" {
  for_each           = var.enabled ? local.permission_sets : {}
  scope              = each.key == "chat" ? var.model_account_id : azurerm_cognitive_account_project.evaluation[0].id
  role_definition_id = azurerm_role_definition.operator[each.key].role_definition_resource_id
  principal_id       = var.operator_principal_id
  principal_type     = "User"
}
