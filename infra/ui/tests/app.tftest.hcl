mock_provider "azurerm" {
  mock_data "azurerm_container_app_environment" {
    defaults = {
      id             = "/subscriptions/${uuidv5("dns", "test/subscription")}/resourceGroups/rg-newsloom-test/providers/Microsoft.App/managedEnvironments/cae-newsloom-test"
      default_domain = "owned.francecentral.azurecontainerapps.io"
      location       = "francecentral"
    }
  }
}
variables {
  enabled                      = true
  subscription_id              = uuidv5("dns", "test/subscription")
  environment_name             = "test"
  resource_group_name          = "rg-newsloom-test"
  container_app_environment_id = "/subscriptions/${uuidv5("dns", "test/subscription")}/resourceGroups/rg-newsloom-test/providers/Microsoft.App/managedEnvironments/cae-newsloom-test"
  registry_id                  = "/subscriptions/${uuidv5("dns", "test/subscription")}/resourceGroups/rg-newsloom-test/providers/Microsoft.ContainerRegistry/registries/acrnewsloomtest${substr(sha256("${uuidv5("dns", "test/subscription")}/test"), 0, 8)}"
  registry_endpoint            = "acrnewsloomtest${substr(sha256("${uuidv5("dns", "test/subscription")}/test"), 0, 8)}.azurecr.io"
  image                        = "acrnewsloomtest${substr(sha256("${uuidv5("dns", "test/subscription")}/test"), 0, 8)}.azurecr.io/newsloom-web@sha256:${sha256("test/image")}"
  image_revision               = sha256("test/source")
  config_base64 = base64encode(jsonencode({
    tenantId   = uuidv5("dns", "test/tenant")
    clientId   = uuidv5("dns", "test/ui")
    agentUrl   = "https://agent.test/a2a"
    agentScope = "api://${uuidv5("dns", "test/agent")}/news.agent"
  }))
}
run "disabled_is_empty" {
  command = plan
  variables { enabled = false }
  assert {
    condition     = length(azurerm_container_app.ui) == 0
    error_message = "The UI app must be explicitly enabled."
  }
}
run "static_ui_has_only_registry_authority" {
  command = plan
  assert {
    condition = (
      azurerm_container_app.ui[0].template[0].min_replicas == 0 &&
      azurerm_container_app.ui[0].template[0].max_replicas == 1 &&
      azurerm_container_app.ui[0].template[0].container[0].cpu == 0.25 &&
      azurerm_container_app.ui[0].template[0].container[0].memory == "0.5Gi" &&
      azurerm_container_app.ui[0].template[0].container[0].image == var.image &&
      !azurerm_container_app.ui[0].ingress[0].allow_insecure_connections &&
      azurerm_container_app.ui[0].ingress[0].target_port == 8080 &&
      azurerm_role_assignment.registry[0].role_definition_name == "AcrPull" &&
      azurerm_role_assignment.registry[0].scope == var.registry_id &&
      length(local.environment) == 3 &&
      !contains(keys(local.environment), "AZURE_CLIENT_SECRET") &&
      !contains(keys(local.environment), "POSTGRES_HOST")
    )
    error_message = "The small HTTPS static UI must have only its own registry pull."
  }
}
run "reject_mutable_image" {
  command = plan
  variables { image = "registry.test/newsloom-web:latest" }
  expect_failures = [var.image]
}
run "reject_broken_runtime_config" {
  command = plan
  variables { config_base64 = "invalid" }
  expect_failures = [var.config_base64]
}
run "news_config_has_separate_audiences_without_new_resources" {
  command = plan
  variables {
    news_enabled = true
    config_base64 = base64encode(jsonencode({
      tenantId   = uuidv5("dns", "test/tenant")
      clientId   = uuidv5("dns", "test/ui")
      agentUrl   = "https://agent.test/a2a"
      agentScope = "api://${uuidv5("dns", "test/agent")}/news.agent"
      mcpUrl     = "https://mcp.test/mcp"
      mcpScope   = "api://${uuidv5("dns", "test/mcp")}/news.read"
    }))
  }
  assert {
    condition = (
      length(azurerm_container_app.ui) == 1 &&
      length(local.environment) == 4 &&
      local.environment.MCP_ORIGIN == "https://mcp.test" &&
      local.environment.AGENT_ORIGIN == "https://agent.test"
    )
    error_message = "The retained UI must only add its trusted MCP configuration."
  }
}
