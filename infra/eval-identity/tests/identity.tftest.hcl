mock_provider "azurerm" {}

variables {
  subscription_id     = join("-", ["00000000", "0000", "0000", "0000", "000000000000"])
  environment_name    = "test"
  resource_group_name = "rg-newsloom-test"
  location            = "francecentral"
  model_account_id    = "/subscriptions/test/resourceGroups/rg-newsloom-test/providers/Microsoft.CognitiveServices/accounts/ai-newsloom-test"
}

run "disabled_by_default" {
  command = plan
  assert {
    condition = (
      length(azurerm_user_assigned_identity.eval) == 0 &&
      length(azurerm_federated_identity_credential.github) == 0 &&
      length(azurerm_role_assignment.chat) == 0 &&
      output.EVAL_IDENTITY_CLIENT_ID == ""
    )
    error_message = "Nothing exists unless live evals are enabled."
  }
}

run "pull_request_and_main_federation_with_chat_only" {
  command = plan
  variables {
    enabled = true
  }
  assert {
    condition     = toset(keys(azurerm_federated_identity_credential.github)) == toset(["pull-request", "main"])
    error_message = "One credential for pull requests and one for main."
  }
  assert {
    condition     = azurerm_federated_identity_credential.github["pull-request"].subject == "repo:ikhemissi@1769608/newsloom@1429962749:pull_request" && azurerm_federated_identity_credential.github["main"].subject == "repo:ikhemissi@1769608/newsloom@1429962749:ref:refs/heads/main"
    error_message = "Subjects are the immutable-ID pull_request and main subjects."
  }
  assert {
    condition     = azurerm_federated_identity_credential.github["main"].issuer == "https://token.actions.githubusercontent.com" && contains(azurerm_federated_identity_credential.github["main"].audience, "api://AzureADTokenExchange") && length(azurerm_federated_identity_credential.github["main"].audience) == 1
    error_message = "GitHub issuer and the token-exchange audience only."
  }
  assert {
    condition     = toset(azurerm_role_definition.chat[0].permissions[0].data_actions) == toset(["Microsoft.CognitiveServices/accounts/OpenAI/deployments/chat/completions/action"]) && length(azurerm_role_definition.chat[0].permissions[0].actions) == 0
    error_message = "Chat completions only."
  }
  assert {
    condition     = azurerm_role_assignment.chat[0].scope == var.model_account_id
    error_message = "Granted on the model account only."
  }
}

run "other_subjects_are_rejected" {
  command = plan
  variables {
    enabled         = true
    github_subjects = ["repo:someone/fork:pull_request"]
  }
  expect_failures = [var.github_subjects]
}
