mock_provider "azurerm" {}

variables {
  subscription_id        = join("-", ["00000000", "0000", "0000", "0000", "000000000000"])
  environment_name       = "test"
  resource_group_name    = "rg-newsloom-test"
  location               = "francecentral"
  registry_id            = "/subscriptions/test/resourceGroups/test/providers/Microsoft.ContainerRegistry/registries/existing"
  applicationinsights_id = "/subscriptions/test/resourceGroups/test/providers/Microsoft.Insights/components/existing"
  model_account_id       = "/subscriptions/test/resourceGroups/test/providers/Microsoft.CognitiveServices/accounts/existing"
  enrichment_deployment  = "existing-enrichment"
  generation_deployment  = "briefing"
  generation_model       = "existing-pinned-model"
  generation_version     = "existing-pinned-version"
  generation_sku         = "Standard"
}

run "disabled_by_default" {
  command = plan
  assert {
    condition = (
      length(azurerm_user_assigned_identity.briefing) == 0 &&
      length(azurerm_cognitive_deployment.briefing) == 0 &&
      length(azurerm_role_definition.chat) == 0 &&
      length(azurerm_role_assignment.chat) == 0 &&
      length(azurerm_role_assignment.registry) == 0 &&
      length(azurerm_role_assignment.telemetry) == 0 &&
      output.BRIEFING_IDENTITY_BASE64 == ""
    )
    error_message = "No briefing resources or grants exist by default."
  }
}

run "additive_pinned_model_and_minimal_grants" {
  command = plan
  variables {
    enabled = true
  }
  assert {
    condition = (
      azurerm_user_assigned_identity.briefing[0].name == "id-newsloom-test-briefing" &&
      azurerm_user_assigned_identity.briefing[0].location == var.location &&
      azurerm_cognitive_deployment.briefing[0].cognitive_account_id == var.model_account_id &&
      azurerm_cognitive_deployment.briefing[0].name != var.enrichment_deployment &&
      azurerm_cognitive_deployment.briefing[0].model[0].name == var.generation_model &&
      azurerm_cognitive_deployment.briefing[0].model[0].version == var.generation_version &&
      azurerm_cognitive_deployment.briefing[0].version_upgrade_option == "NoAutoUpgrade" &&
      azurerm_cognitive_deployment.briefing[0].sku[0].capacity == 10 &&
      azurerm_role_assignment.chat[0].scope == var.model_account_id &&
      azurerm_role_assignment.registry[0].scope == var.registry_id &&
      azurerm_role_assignment.registry[0].role_definition_name == "AcrPull" &&
      azurerm_role_assignment.telemetry[0].scope == var.applicationinsights_id &&
      azurerm_role_assignment.telemetry[0].role_definition_name == "Monitoring Metrics Publisher" &&
      toset(azurerm_role_definition.chat[0].permissions[0].data_actions) == toset(["Microsoft.CognitiveServices/accounts/OpenAI/deployments/chat/completions/action"]) &&
      length(azurerm_role_definition.chat[0].permissions[0].actions) == 0
    )
    error_message = "Use only the dedicated identity, pinned separate capacity-10 deployment and narrowly scoped grants."
  }
}

run "reject_reused_enrichment_deployment" {
  command = plan
  variables {
    enabled               = true
    generation_deployment = "existing-enrichment"
  }
  expect_failures = [var.generation_deployment]
}
