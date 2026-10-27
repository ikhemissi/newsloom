mock_provider "azurerm" {
  mock_data "azurerm_client_config" {
    defaults = {
      tenant_id       = uuidv5("dns", "test/tenant")
      subscription_id = uuidv5("dns", "test/subscription")
    }
  }
  mock_resource "azurerm_user_assigned_identity" {
    defaults = {
      principal_id = uuidv5("dns", "test/agent-principal")
      client_id    = uuidv5("dns", "test/agent-mi-client")
    }
  }
  mock_resource "azurerm_role_definition" {
    defaults = {
      role_definition_resource_id = "/subscriptions/${uuidv5("dns", "test/subscription")}/providers/Microsoft.Authorization/roleDefinitions/${uuidv5("dns", "test/chat-role")}"
    }
  }
}
override_resource {
  target = azuread_application.api[0]
  values = {
    id        = "/applications/${uuidv5("dns", "test/agent-api-object")}"
    client_id = uuidv5("dns", "test/agent-api-client")
    object_id = uuidv5("dns", "test/agent-api-object")
  }
}
override_resource {
  target = azuread_application.client[0]
  values = {
    id        = "/applications/${uuidv5("dns", "test/agent-client-object")}"
    client_id = uuidv5("dns", "test/agent-client")
    object_id = uuidv5("dns", "test/agent-client-object")
  }
}
override_resource {
  target = azuread_service_principal.api[0]
  values = {
    object_id = uuidv5("dns", "test/agent-api-principal")
  }
}
override_resource {
  target = azuread_service_principal.client[0]
  values = {
    object_id = uuidv5("dns", "test/agent-client-principal")
  }
}
mock_provider "azuread" {
  mock_data "azuread_client_config" {
    defaults = {
      tenant_id = uuidv5("dns", "test/tenant")
      object_id = uuidv5("dns", "test/operator")
    }
  }
  mock_data "azuread_service_principal" {
    defaults = {
      client_id             = uuidv5("dns", "test/mcp-client")
      object_id             = uuidv5("dns", "test/mcp-principal")
      application_tenant_id = uuidv5("dns", "test/tenant")
      account_enabled       = true
      oauth2_permission_scope_ids = {
        "news.read" = uuidv5("dns", "test/mcp-scope")
      }
      app_role_ids = {}
    }
  }
}
variables {
  enabled                = true
  consent_enabled        = true
  tenant_id              = uuidv5("dns", "test/tenant")
  subscription_id        = uuidv5("dns", "test/subscription")
  environment_name       = "test"
  resource_group_name    = "rg-newsloom-test"
  location               = "swedencentral"
  registry_id            = "/subscriptions/${uuidv5("dns", "test/subscription")}/resourceGroups/rg-newsloom-test/providers/Microsoft.ContainerRegistry/registries/acrnewsloomtest${substr(sha256("${uuidv5("dns", "test/subscription")}/test"), 0, 8)}"
  model_account_id       = "/subscriptions/${uuidv5("dns", "test/subscription")}/resourceGroups/rg-newsloom-test/providers/Microsoft.CognitiveServices/accounts/ai-newsloom-test-${substr(sha256("${uuidv5("dns", "test/subscription")}/test"), 0, 8)}"
  applicationinsights_id = "/subscriptions/${uuidv5("dns", "test/subscription")}/resourceGroups/rg-newsloom-test/providers/Microsoft.Insights/components/appi-newsloom-test"
  mcp_api_client_id      = uuidv5("dns", "test/mcp-client")
  mcp_api_principal_id   = uuidv5("dns", "test/mcp-principal")
  mcp_scope_id           = uuidv5("dns", "test/mcp-scope")
}

run "disabled_is_no_resources" {
  command = plan
  variables {
    enabled = false
  }
  assert {
    condition = (
      length(azurerm_user_assigned_identity.agent) == 0 &&
      length(azuread_application.api) == 0 &&
      length(azuread_application.client) == 0 &&
      length(azurerm_role_assignment.chat) == 0 &&
      length(azurerm_role_assignment.registry) == 0 &&
      length(azurerm_role_assignment.telemetry) == 0 &&
      length(azuread_service_principal_delegated_permission_grant.mcp) == 0 &&
      length(azuread_service_principal_delegated_permission_grant.client) == 0
    )
    error_message = "Disabled layers must add no resources or consent, even when consent is set."
  }
}
run "exact_federation_separate_apis_and_only_delegated_scopes" {
  command = apply
  assert {
    condition = (
      azurerm_user_assigned_identity.agent[0].name == "id-newsloom-test-agent" &&
      azuread_application_federated_identity_credential.managed_identity[0].issuer == "https://login.microsoftonline.com/${var.tenant_id}/v2.0" &&
      azuread_application_federated_identity_credential.managed_identity[0].subject == azurerm_user_assigned_identity.agent[0].principal_id &&
      toset(azuread_application_federated_identity_credential.managed_identity[0].audiences) == toset(["api://AzureADTokenExchange"]) &&
      azuread_application.api[0].sign_in_audience == "AzureADMyOrg" &&
      azuread_application.api[0].api[0].requested_access_token_version == 2 &&
      one(azuread_application.api[0].api[0].oauth2_permission_scope).value == "news.agent" &&
      one(azuread_application.api[0].api[0].oauth2_permission_scope).id == uuidv5("dns", "newsloom-test/news.agent") &&
      output.AGENT_INVOKE_SCOPE == "api://${azuread_application.api[0].client_id}/news.agent" &&
      azuread_application.api[0].client_id != var.mcp_api_client_id &&
      azuread_application.client[0].client_id != azuread_application.api[0].client_id &&
      azuread_application.client[0].fallback_public_client_enabled &&
      toset(azuread_application.client[0].public_client[0].redirect_uris) == toset(["http://127.0.0.1:8400/callback"]) &&
      length(azuread_application.api[0].required_resource_access) == 1 &&
      one(azuread_application.api[0].required_resource_access).resource_app_id == var.mcp_api_client_id &&
      one(one(azuread_application.api[0].required_resource_access).resource_access).type == "Scope" &&
      toset(azuread_service_principal_delegated_permission_grant.mcp[0].claim_values) == toset(["news.read"]) &&
      toset(azuread_service_principal_delegated_permission_grant.client[0].claim_values) == toset(["news.agent"])
    )
    error_message = "Only exact same-tenant MI federation, separate registrations and the two delegated consents are allowed."
  }
  assert {
    condition = (
      length(azurerm_role_definition.chat[0].permissions) == 1 &&
      length(one(azurerm_role_definition.chat[0].permissions).actions) == 0 &&
      toset(one(azurerm_role_definition.chat[0].permissions).data_actions) == toset(["Microsoft.CognitiveServices/accounts/OpenAI/deployments/chat/completions/action"]) &&
      azurerm_role_assignment.chat[0].scope == var.model_account_id &&
      azurerm_role_assignment.registry[0].scope == var.registry_id &&
      azurerm_role_assignment.registry[0].role_definition_name == "AcrPull" &&
      azurerm_role_assignment.telemetry[0].scope == var.applicationinsights_id &&
      azurerm_role_assignment.telemetry[0].role_definition_name == "Monitoring Metrics Publisher" &&
      azurerm_role_assignment.chat[0].principal_id == azurerm_user_assigned_identity.agent[0].principal_id
    )
    error_message = "The separate identity receives only owning registry, telemetry and chat operations."
  }
}
run "consent_requires_separate_opt_in" {
  command = plan
  variables {
    consent_enabled = false
  }
  assert {
    condition     = length(azuread_service_principal_delegated_permission_grant.mcp) == 0 && length(azuread_service_principal_delegated_permission_grant.client) == 0
    error_message = "Registration intent does not silently grant tenant-wide delegated consent."
  }
}
run "reject_wildcard_callback" {
  command = plan
  variables {
    redirect_uris = ["http://localhost:*"]
  }
  expect_failures = [var.redirect_uris]
}
run "reject_foreign_resource_scope" {
  command = plan
  variables {
    model_account_id = "/subscriptions/other/resourceGroups/other"
  }
  expect_failures = [var.model_account_id]
}
run "reject_foreign_tenant" {
  command = plan
  variables {
    tenant_id = uuidv5("dns", "foreign/tenant")
  }
  expect_failures = [data.azuread_client_config.current, data.azurerm_client_config.current, data.azuread_service_principal.mcp]
}
run "reject_wrong_mcp_api" {
  command = plan
  variables {
    mcp_api_client_id = uuidv5("dns", "wrong/client")
  }
  expect_failures = [data.azuread_service_principal.mcp]
}
run "reject_wrong_mcp_scope" {
  command = plan
  variables {
    mcp_scope_id = uuidv5("dns", "wrong/scope")
  }
  expect_failures = [data.azuread_service_principal.mcp]
}
run "reject_invalid_ids" {
  command = plan
  variables {
    mcp_scope_id = "------------------------------------"
  }
  expect_failures = [var.mcp_scope_id]
}
run "reject_application_permission_on_mcp" {
  command = plan
  override_data {
    target = data.azuread_service_principal.mcp[0]
    values = {
      client_id             = uuidv5("dns", "test/mcp-client")
      object_id             = uuidv5("dns", "test/mcp-principal")
      application_tenant_id = uuidv5("dns", "test/tenant")
      account_enabled       = true
      oauth2_permission_scope_ids = {
        "news.read" = uuidv5("dns", "test/mcp-scope")
      }
      app_role_ids = { "news.read" = uuidv5("dns", "test/mcp-application-role") }
    }
  }
  expect_failures = [data.azuread_service_principal.mcp]
}
run "reject_extra_mcp_scope" {
  command = plan
  override_data {
    target = data.azuread_service_principal.mcp[0]
    values = {
      client_id             = uuidv5("dns", "test/mcp-client")
      object_id             = uuidv5("dns", "test/mcp-principal")
      application_tenant_id = uuidv5("dns", "test/tenant")
      account_enabled       = true
      oauth2_permission_scope_ids = {
        "news.read"  = uuidv5("dns", "test/mcp-scope")
        "news.write" = uuidv5("dns", "test/mcp-write-scope")
      }
      app_role_ids = {}
    }
  }
  expect_failures = [data.azuread_service_principal.mcp]
}
run "reject_foreign_registry" {
  command = plan
  variables {
    registry_id = "/subscriptions/other/providers/Microsoft.ContainerRegistry/registries/other"
  }
  expect_failures = [var.registry_id]
}
run "reject_foreign_telemetry" {
  command = plan
  variables {
    applicationinsights_id = "/subscriptions/other/providers/Microsoft.Insights/components/other"
  }
  expect_failures = [var.applicationinsights_id]
}
run "reject_lookalike_callback" {
  command = plan
  variables {
    redirect_uris = ["http://localhost.attacker.invalid:8400/callback"]
  }
  expect_failures = [var.redirect_uris]
}
run "reject_incoherent_adoption" {
  command = plan
  variables {
    adoption = {
      api_object_id       = uuidv5("dns", "test/adoption-api-object")
      api_client_id       = ""
      api_principal_id    = ""
      scope_id            = ""
      client_object_id    = ""
      client_client_id    = ""
      client_principal_id = ""
      federation_id       = ""
      mcp_consent_id      = ""
      client_consent_id   = ""
    }
  }
  expect_failures = [var.adoption]
}
