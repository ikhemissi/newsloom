mock_provider "azurerm" {
  mock_resource "azurerm_cognitive_account_project" {
    defaults = {
      id = "/subscriptions/test/resourceGroups/rg-newsloom-test/providers/Microsoft.CognitiveServices/accounts/ai-newsloom-test/projects/research-newsloom-test"
    }
  }
}

variables {
  subscription_id     = join("-", ["00000000", "0000", "0000", "0000", "000000000000"])
  environment_name    = "test"
  resource_group_name = "rg-newsloom-test"
  location            = "francecentral"
  model_account_id    = "/subscriptions/test/resourceGroups/rg-newsloom-test/providers/Microsoft.CognitiveServices/accounts/ai-newsloom-test"
  agent_identity_base64 = base64encode(jsonencode({
    id           = "/subscriptions/test/resourceGroups/test/providers/Microsoft.ManagedIdentity/userAssignedIdentities/agent"
    client_id    = join("-", ["00000000", "0000", "0000", "0000", "000000000002"])
    principal_id = join("-", ["00000000", "0000", "0000", "0000", "000000000003"])
  }))
}

run "disabled_by_default" {
  command = plan
  assert {
    condition     = length(azurerm_cognitive_account_project.research) == 0 && length(azurerm_role_assignment.agent) == 0 && output.WEB_RESEARCH_PROJECT_ENDPOINT == ""
    error_message = "Web research creates nothing unless enabled."
  }
}

run "dedicated_project_and_project_scoped_agent_grant" {
  command = apply
  variables {
    enabled              = true
    foundry_user_role_id = join("-", ["53ca6127", "db72", "4b80", "b1b0", "d745d6d5456d"])
  }
  assert {
    condition = (
      azurerm_cognitive_account_project.research[0].name == "research-newsloom-test" &&
      azurerm_cognitive_account_project.research[0].identity[0].type == "SystemAssigned" &&
      azurerm_role_assignment.agent[0].scope == azurerm_cognitive_account_project.research[0].id &&
      azurerm_role_assignment.agent[0].principal_id == join("-", ["00000000", "0000", "0000", "0000", "000000000003"]) &&
      output.WEB_RESEARCH_PROJECT_ENDPOINT == "https://ai-newsloom-test.services.ai.azure.com/api/projects/research-newsloom-test"
    )
    error_message = "The agent may use only the dedicated web-research project."
  }
}

run "only_the_documented_role" {
  command = plan
  variables {
    enabled              = true
    foundry_user_role_id = "Owner"
  }
  expect_failures = [var.foundry_user_role_id]
}
