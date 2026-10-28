mock_provider "azurerm" {
  override_during = plan
  mock_data "azurerm_client_config" {
    defaults = {
      subscription_id = uuidv5("dns", "test/subscription")
      tenant_id       = uuidv5("dns", "test/tenant")
      object_id       = uuidv5("dns", "test/operator")
    }
  }
  mock_resource "azurerm_cognitive_account_project" {
    defaults = {
      id = "/subscriptions/${uuidv5("dns", "test/subscription")}/resourceGroups/rg-newsloom-test/providers/Microsoft.CognitiveServices/accounts/ai-newsloom-test-${substr(sha256("${uuidv5("dns", "test/subscription")}/test"), 0, 8)}/projects/eval-newsloom-test"
      identity = {
        principal_id = uuidv5("dns", "test/evaluation-project")
        tenant_id    = uuidv5("dns", "test/tenant")
      }
      endpoints = {
        "AI Foundry API" = "https://ai-newsloom-test-${substr(sha256("${uuidv5("dns", "test/subscription")}/test"), 0, 8)}.services.ai.azure.com/api/projects/eval-newsloom-test"
      }
    }
  }
}

variables {
  enabled               = true
  subscription_id       = uuidv5("dns", "test/subscription")
  tenant_id             = uuidv5("dns", "test/tenant")
  operator_principal_id = uuidv5("dns", "test/operator")
  environment_name      = "test"
  resource_group_name   = "rg-newsloom-test"
  location              = "francecentral"
  model_account_id      = "/subscriptions/${uuidv5("dns", "test/subscription")}/resourceGroups/rg-newsloom-test/providers/Microsoft.CognitiveServices/accounts/ai-newsloom-test-${substr(sha256("${uuidv5("dns", "test/subscription")}/test"), 0, 8)}"
  model_endpoint        = "https://ai-newsloom-test-${substr(sha256("${uuidv5("dns", "test/subscription")}/test"), 0, 8)}.services.ai.azure.com/"
}

run "disabled_has_no_project_or_grants" {
  command = plan
  variables {
    enabled               = false
    operator_principal_id = ""
    tenant_id             = ""
  }
  assert {
    condition = (
      length(azurerm_cognitive_account_project.evaluation) == 0 &&
      length(azurerm_role_definition.operator) == 0 &&
      length(azurerm_role_assignment.operator) == 0 &&
      length(data.azurerm_client_config.current) == 0 &&
      output.AGENT_EVALUATION_PROJECT_ID == "" &&
      output.AGENT_EVALUATION_GRANTS_BASE64 == ""
    )
    error_message = "The disabled layer must not read identity context or create resources or authority."
  }
}

run "one_project_and_only_two_operator_grants" {
  command = plan
  assert {
    condition = (
      length(azurerm_cognitive_account_project.evaluation) == 1 &&
      azurerm_cognitive_account_project.evaluation[0].name == "eval-newsloom-test" &&
      azurerm_cognitive_account_project.evaluation[0].cognitive_account_id == var.model_account_id &&
      azurerm_cognitive_account_project.evaluation[0].location == var.location &&
      azurerm_cognitive_account_project.evaluation[0].identity[0].type == "SystemAssigned" &&
      length(azurerm_role_definition.operator) == 2 &&
      length(azurerm_role_assignment.operator) == 2 &&
      alltrue([for grant in azurerm_role_assignment.operator : grant.principal_id == var.operator_principal_id && grant.principal_type == "User"]) &&
      alltrue([for role in azurerm_role_definition.operator : length(role.permissions[0].actions) == 0 && length(role.permissions[0].not_actions) == 0 && length(role.permissions[0].not_data_actions) == 0])
    )
    error_message = "Create only one child project and two data-only operator grants; no managed-identity or workload grants."
  }
  assert {
    condition = (
      azurerm_role_assignment.operator["chat"].scope == var.model_account_id &&
      azurerm_role_assignment.operator["evaluations"].scope == azurerm_cognitive_account_project.evaluation[0].id &&
      toset(azurerm_role_definition.operator["chat"].permissions[0].data_actions) == toset(["Microsoft.CognitiveServices/accounts/OpenAI/deployments/chat/completions/action"]) &&
      toset(azurerm_role_definition.operator["evaluations"].permissions[0].data_actions) == toset([
        "Microsoft.CognitiveServices/accounts/AIServices/evaluations/read",
        "Microsoft.CognitiveServices/accounts/AIServices/evaluations/write",
        "Microsoft.CognitiveServices/accounts/AIServices/evaluations/delete",
        "Microsoft.CognitiveServices/accounts/OpenAI/evals/read",
        "Microsoft.CognitiveServices/accounts/OpenAI/evals/write",
      ]) &&
      output.AGENT_EVALUATION_PROJECT_ENDPOINT == "${trimsuffix(var.model_endpoint, "/")}/api/projects/eval-newsloom-test"
    )
    error_message = "Chat is account-scoped and chat-only; evaluation operations are confined to the owned project."
  }
}

run "reject_foreign_account" {
  command = plan
  variables {
    model_account_id = "/subscriptions/${uuidv5("dns", "test/subscription")}/resourceGroups/other/providers/Microsoft.CognitiveServices/accounts/other"
  }
  expect_failures = [var.model_account_id]
}

run "reject_account_scope_replaced_with_deployment" {
  command = plan
  variables {
    model_account_id = "/subscriptions/${uuidv5("dns", "test/subscription")}/resourceGroups/rg-newsloom-test/providers/Microsoft.CognitiveServices/accounts/ai-newsloom-test-${substr(sha256("${uuidv5("dns", "test/subscription")}/test"), 0, 8)}/deployments/chat"
  }
  expect_failures = [var.model_account_id]
}

run "reject_foreign_endpoint" {
  command = plan
  variables {
    model_endpoint = "https://other.services.ai.azure.com/"
  }
  expect_failures = [var.model_endpoint]
}

run "reject_missing_operator" {
  command = plan
  variables {
    operator_principal_id = ""
  }
  expect_failures = [var.operator_principal_id]
}

run "reject_other_provider_operator" {
  command = plan
  override_data {
    target = data.azurerm_client_config.current[0]
    values = {
      object_id = uuidv5("dns", "test/foreign-operator")
    }
  }
  expect_failures = [data.azurerm_client_config.current]
}

run "reject_other_provider_tenant" {
  command = plan
  override_data {
    target = data.azurerm_client_config.current[0]
    values = {
      tenant_id = uuidv5("dns", "test/foreign-tenant")
    }
  }
  expect_failures = [data.azurerm_client_config.current]
}

run "reject_other_provider_subscription" {
  command = plan
  override_data {
    target = data.azurerm_client_config.current[0]
    values = {
      subscription_id = uuidv5("dns", "test/foreign-subscription")
    }
  }
  expect_failures = [data.azurerm_client_config.current]
}

run "reject_foreign_project_identity_tenant" {
  command = plan
  override_resource {
    target          = azurerm_cognitive_account_project.evaluation[0]
    override_during = plan
    values = {
      id = "/subscriptions/${uuidv5("dns", "test/subscription")}/resourceGroups/rg-newsloom-test/providers/Microsoft.CognitiveServices/accounts/ai-newsloom-test-${substr(sha256("${uuidv5("dns", "test/subscription")}/test"), 0, 8)}/projects/eval-newsloom-test"
      identity = {
        principal_id = uuidv5("dns", "test/evaluation-project")
        tenant_id    = uuidv5("dns", "test/foreign-tenant")
      }
    }
  }
  expect_failures = [azurerm_cognitive_account_project.evaluation]
}

run "reject_operator_reused_as_project_identity" {
  command = plan
  override_resource {
    target          = azurerm_cognitive_account_project.evaluation[0]
    override_during = plan
    values = {
      id = "/subscriptions/${uuidv5("dns", "test/subscription")}/resourceGroups/rg-newsloom-test/providers/Microsoft.CognitiveServices/accounts/ai-newsloom-test-${substr(sha256("${uuidv5("dns", "test/subscription")}/test"), 0, 8)}/projects/eval-newsloom-test"
      identity = {
        principal_id = uuidv5("dns", "test/operator")
        tenant_id    = uuidv5("dns", "test/tenant")
      }
    }
  }
  expect_failures = [azurerm_cognitive_account_project.evaluation]
}

run "apply_outputs_and_grant_inventory" {
  command = apply
  assert {
    condition = (
      jsondecode(base64decode(output.AGENT_EVALUATION_GRANTS_BASE64)).chat.principal_id == var.operator_principal_id &&
      jsondecode(base64decode(output.AGENT_EVALUATION_GRANTS_BASE64)).evaluations.scope == output.AGENT_EVALUATION_PROJECT_ID &&
      output.AGENT_EVALUATION_PROJECT_PRINCIPAL_ID != var.operator_principal_id &&
      jsondecode(base64decode(output.AGENT_EVALUATION_PROJECT_ENDPOINTS_BASE64))["AI Foundry API"] == output.AGENT_EVALUATION_PROJECT_ENDPOINT
    )
    error_message = "The private outputs must retain exact native endpoints, distinct project identity and operator-only authority."
  }
}
