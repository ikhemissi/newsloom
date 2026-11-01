mock_provider "azurerm" {
  mock_data "azurerm_container_app_environment" {
    defaults = {
      id             = "/subscriptions/${uuidv5("dns", "test/subscription")}/resourceGroups/rg-newsloom-test/providers/Microsoft.App/managedEnvironments/cae-newsloom-test"
      default_domain = "owned.francecentral.azurecontainerapps.io"
    }
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
      client_id                   = uuidv5("dns", "test/agent")
      application_tenant_id       = uuidv5("dns", "test/tenant")
      account_enabled             = true
      oauth2_permission_scope_ids = { "news.agent" = uuidv5("dns", "test/scope") }
      app_role_ids                = {}
    }
  }
}
variables {
  enabled                      = true
  consent_enabled              = true
  subscription_id              = uuidv5("dns", "test/subscription")
  tenant_id                    = uuidv5("dns", "test/tenant")
  environment_name             = "test"
  resource_group_name          = "rg-newsloom-test"
  container_app_environment_id = "/subscriptions/${uuidv5("dns", "test/subscription")}/resourceGroups/rg-newsloom-test/providers/Microsoft.App/managedEnvironments/cae-newsloom-test"
  agent_api_client_id          = uuidv5("dns", "test/agent")
  agent_api_principal_id       = uuidv5("dns", "test/agent-principal")
  agent_scope_id               = uuidv5("dns", "test/scope")
}
run "disabled_is_empty" {
  command = plan
  variables { enabled = false }
  assert {
    condition     = length(azuread_application.client) == 0 && output.UI_ORIGIN == ""
    error_message = "UI identity is explicitly opt-in."
  }
}
run "separate_spa_has_only_the_agent_permission" {
  command = plan
  assert {
    condition = (
      azuread_application.client[0].sign_in_audience == "AzureADMyOrg" &&
      !azuread_application.client[0].fallback_public_client_enabled &&
      azuread_application.client[0].single_page_application[0].redirect_uris == toset([
        "${local.origin}/auth/callback", "${local.origin}/"
      ]) &&
      length(azuread_application.client[0].required_resource_access) == 1 &&
      one(azuread_application.client[0].required_resource_access).resource_app_id == var.agent_api_client_id &&
      azuread_service_principal_delegated_permission_grant.agent[0].claim_values == toset(["news.agent"])
    )
    error_message = "Only an exact-origin SPA with delegated news.agent is permitted."
  }
}
run "consent_is_explicit" {
  command = plan
  variables { consent_enabled = false }
  assert {
    condition     = length(azuread_service_principal_delegated_permission_grant.agent) == 0
    error_message = "No consent is provisioned without explicit opt-in."
  }
}
run "reject_foreign_environment" {
  command = plan
  variables { container_app_environment_id = "/foreign/environment" }
  expect_failures = [var.container_app_environment_id]
}
run "news_adds_only_the_existing_mcp_delegated_scope" {
  command = plan
  variables {
    news_enabled         = true
    mcp_api_client_id    = uuidv5("dns", "test/mcp")
    mcp_api_principal_id = uuidv5("dns", "test/mcp-principal")
    mcp_scope_id         = uuidv5("dns", "test/mcp-scope")
  }
  override_data {
    target = data.azuread_service_principal.mcp[0]
    values = {
      client_id                   = uuidv5("dns", "test/mcp")
      application_tenant_id       = uuidv5("dns", "test/tenant")
      account_enabled             = true
      oauth2_permission_scope_ids = { "news.read" = uuidv5("dns", "test/mcp-scope") }
      app_role_ids                = {}
    }
  }
  assert {
    condition = (
      length(azuread_application.client[0].required_resource_access) == 2 &&
      azuread_service_principal_delegated_permission_grant.agent[0].claim_values == toset(["news.agent"]) &&
      azuread_service_principal_delegated_permission_grant.mcp[0].claim_values == toset(["news.read"]) &&
      azuread_application.client[0].single_page_application[0].redirect_uris == toset([
        "${local.origin}/auth/callback", "${local.origin}/"
      ])
    )
    error_message = "News must only add MCP delegated access and preserve agent access and redirects."
  }
}
