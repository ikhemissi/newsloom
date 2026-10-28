mock_provider "azurerm" {
  mock_data "azurerm_container_app_environment" {
    defaults = {
      id             = "/subscriptions/${uuidv5("dns", "test/subscription")}/resourceGroups/rg-newsloom-test/providers/Microsoft.App/managedEnvironments/cae-newsloom-test"
      default_domain = "owned.swedencentral.azurecontainerapps.io"
    }
  }
}
variables {
  enabled                      = true
  subscription_id              = uuidv5("dns", "test/subscription")
  tenant_id                    = uuidv5("dns", "test/tenant")
  api_client_id                = uuidv5("dns", "test/agent-api")
  environment_name             = "test"
  resource_group_name          = "rg-newsloom-test"
  container_app_environment_id = "/subscriptions/${uuidv5("dns", "test/subscription")}/resourceGroups/rg-newsloom-test/providers/Microsoft.App/managedEnvironments/cae-newsloom-test"
  registry_endpoint            = "acrnewsloomtest${substr(sha256("${uuidv5("dns", "test/subscription")}/test"), 0, 8)}.azurecr.io"
  identity_base64 = base64encode(jsonencode({
    id           = "/subscriptions/${uuidv5("dns", "test/subscription")}/resourceGroups/rg-newsloom-test/providers/Microsoft.ManagedIdentity/userAssignedIdentities/id-newsloom-test-agent"
    client_id    = uuidv5("dns", "test/agent-mi")
    principal_id = uuidv5("dns", "test/agent-principal")
  }))
  image                                 = "acrnewsloomtest${substr(sha256("${uuidv5("dns", "test/subscription")}/test"), 0, 8)}.azurecr.io/newsloom-agent@sha256:${sha256("test/image")}"
  image_revision                        = sha256("test/source")
  mcp_api_client_id                     = uuidv5("dns", "test/mcp-api")
  mcp_resource_url                      = "https://mcp.owned.swedencentral.azurecontainerapps.io/mcp"
  model_endpoint                        = "https://owned.services.ai.azure.com/"
  chat_deployment                       = "existing-chat"
  applicationinsights_connection_string = "InstrumentationKey=${uuidv5("dns", "test/routing")};IngestionEndpoint=https://francecentral-0.in.applicationinsights.azure.com/"
}
run "disabled_has_no_app" {
  command = plan
  variables {
    enabled = false
  }
  assert {
    condition     = length(azurerm_container_app.agent) == 0 && output.AGENT_RESOURCE_URL == ""
    error_message = "Agent creation is explicitly opt-in."
  }
}
run "one_owned_small_https_immutable_streaming_app" {
  command = plan
  assert {
    condition = (
      length(azurerm_container_app.agent) == 1 &&
      azurerm_container_app.agent[0].workload_profile_name == "Consumption" &&
      azurerm_container_app.agent[0].revision_mode == "Single" &&
      azurerm_container_app.agent[0].template[0].min_replicas == 1 &&
      azurerm_container_app.agent[0].template[0].max_replicas == 1 &&
      azurerm_container_app.agent[0].template[0].container[0].cpu == 0.25 &&
      azurerm_container_app.agent[0].template[0].container[0].memory == "0.5Gi" &&
      azurerm_container_app.agent[0].template[0].container[0].image == var.image &&
      !azurerm_container_app.agent[0].ingress[0].allow_insecure_connections &&
      azurerm_container_app.agent[0].ingress[0].target_port == 8000 &&
      azurerm_container_app.agent[0].identity[0].identity_ids == toset([jsondecode(base64decode(var.identity_base64)).id]) &&
      azurerm_container_app.agent[0].template[0].container[0].readiness_probe[0].path == "/health/live" &&
      output.AGENT_RESOURCE_URL == "https://agent-newsloom-test.owned.swedencentral.azurecontainerapps.io/a2a"
    )
    error_message = "Only the immutable agent app, separate identity and approved one-replica HTTPS profile are allowed."
  }
  assert {
    condition = (
      local.environment.AZURE_CLIENT_ID == jsondecode(base64decode(var.identity_base64)).client_id &&
      local.environment.MCP_RESOURCE_URL == var.mcp_resource_url &&
      local.environment.AGENT_RUNTIME_REVISION == var.image_revision &&
      local.environment.AGENT_RESEARCH_ENABLED == "false" &&
      local.environment.AGENT_ALLOWED_ORIGINS == "" &&
      !contains(keys(local.environment), "POSTGRES_HOST") &&
      local.environment.MODEL_ENDPOINT == var.model_endpoint &&
      local.environment.AGENT_CHAT_DEPLOYMENT == var.chat_deployment &&
      one([for value in azurerm_container_app.agent[0].template[0].container[0].env : value.value if value.name == "APPLICATIONINSIGHTS_CONNECTION_STRING"]) == var.applicationinsights_connection_string &&
      !contains(keys(local.environment), "AZURE_CLIENT_SECRET")
    )
    error_message = "The agent must have only its trusted identity, fixed MCP/chat and authenticated telemetry configuration."
  }
}
run "research_changes_only_the_existing_app_setting" {
  command = plan
  variables {
    research_enabled = true
  }
  assert {
    condition = (
      length(azurerm_container_app.agent) == 1 &&
      local.environment.AGENT_RESEARCH_ENABLED == "true" &&
      azurerm_container_app.agent[0].template[0].container[0].cpu == 0.25 &&
      azurerm_container_app.agent[0].template[0].container[0].memory == "0.5Gi" &&
      azurerm_container_app.agent[0].template[0].container[0].image == var.image
    )
    error_message = "Research must only configure the retained owning app, not widen its profile."
  }
}
run "research_requires_enabled_agent" {
  command = plan
  variables {
    enabled          = false
    research_enabled = true
  }
  expect_failures = [var.research_enabled]
}
run "reject_mutable_image" {
  command = plan
  variables {
    image = "registry.azurecr.io/newsloom-agent:latest"
  }
  expect_failures = [var.image]
}
run "reject_other_service_image" {
  command = plan
  variables {
    image = "registry.azurecr.io/newsloom-mcp@sha256:${sha256("test/image")}"
  }
  expect_failures = [var.image]
}
run "reject_wrong_source_revision" {
  command = plan
  variables {
    image_revision = "main"
  }
  expect_failures = [var.image_revision]
}
run "reject_foreign_identity" {
  command = plan
  variables {
    identity_base64 = base64encode(jsonencode({
      id           = "/subscriptions/other/identity"
      client_id    = uuidv5("dns", "test/mi")
      principal_id = uuidv5("dns", "test/principal")
    }))
  }
  expect_failures = [var.identity_base64]
}
run "reject_broken_identity_encoding" {
  command = plan
  variables {
    identity_base64 = "invalid-encoding"
  }
  expect_failures = [var.identity_base64]
}
run "reject_foreign_environment" {
  command = plan
  variables {
    container_app_environment_id = "/subscriptions/other/managedEnvironments/foreign"
  }
  expect_failures = [var.container_app_environment_id]
}
run "reject_browser_wildcard" {
  command = plan
  variables {
    allowed_origins = ["https://*.untrusted.invalid"]
  }
  expect_failures = [var.allowed_origins]
}
run "reject_untrusted_mcp_endpoint" {
  command = plan
  variables {
    mcp_resource_url = "https://untrusted.invalid/mcp?redirect=other"
  }
  expect_failures = [var.mcp_resource_url]
}
run "reject_model_path_override" {
  command = plan
  variables {
    model_endpoint = "https://owned.services.ai.azure.com/openai/responses"
  }
  expect_failures = [var.model_endpoint]
}
run "reject_model_deployment_url" {
  command = plan
  variables {
    chat_deployment = "https://untrusted.invalid"
  }
  expect_failures = [var.chat_deployment]
}
run "require_telemetry_routing" {
  command = plan
  variables {
    applicationinsights_connection_string = ""
  }
  expect_failures = [var.applicationinsights_connection_string]
}
