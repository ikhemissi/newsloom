mock_provider "azurerm" {
  mock_data "azurerm_container_app_environment" {
    defaults = {
      default_domain = "test.francecentral.azurecontainerapps.io"
    }
  }
}
variables {
  subscription_id              = join("-", ["00000000", "0000", "0000", "0000", "000000000000"])
  tenant_id                    = join("-", ["00000000", "0000", "0000", "0000", "000000000001"])
  api_client_id                = join("-", ["00000000", "0000", "0000", "0000", "000000000002"])
  environment_name             = "test"
  resource_group_name          = "rg-newsloom-test"
  location                     = "francecentral"
  container_app_environment_id = "/subscriptions/${join("-", ["00000000", "0000", "0000", "0000", "000000000000"])}/resourceGroups/rg-newsloom-test/providers/Microsoft.App/managedEnvironments/test"
  registry_endpoint            = "test.azurecr.io"
  image                        = "test.azurecr.io/newsloom-mcp@sha256:${join("", [for n in range(64) : "a"])}"
  workload_identities_base64 = base64encode(jsonencode({
    mcp = {
      id        = "/subscriptions/${join("-", ["00000000", "0000", "0000", "0000", "000000000000"])}/resourceGroups/rg-newsloom-test/providers/Microsoft.ManagedIdentity/userAssignedIdentities/mcp"
      client_id = join("-", ["00000000", "0000", "0000", "0000", "000000000003"])
    }
  }))
  postgres_host                         = "test.postgres.database.azure.com"
  postgres_database                     = "newsloom"
  model_endpoint                        = "https://test.services.ai.azure.com"
  embedding_deployment                  = "embedding"
  embedding_model                       = "text-embedding-3-large"
  embedding_version                     = "1"
  applicationinsights_connection_string = "synthetic-routing-not-a-credential"
}

run "bounded_always_on_app_with_owned_identity" {
  command = plan
  assert {
    condition = (
      azurerm_container_app.mcp.template[0].min_replicas == 1 &&
      azurerm_container_app.mcp.template[0].max_replicas == 1 &&
      azurerm_container_app.mcp.template[0].container[0].image == var.image &&
      azurerm_container_app.mcp.ingress[0].external_enabled &&
      !azurerm_container_app.mcp.ingress[0].allow_insecure_connections &&
      azurerm_container_app.mcp.ingress[0].target_port == 8000 &&
      length(azurerm_container_app.mcp.identity[0].identity_ids) == 1 &&
      azurerm_container_app.mcp.registry[0].password_secret_name == null
    )
    error_message = "Use one small HTTPS app, immutable image and only its existing managed identity."
  }
}
run "resource_url_and_health_match_real_hostname" {
  command = plan
  assert {
    condition = (
      output.MCP_RESOURCE_URL == "https://mcp-newsloom-test.test.francecentral.azurecontainerapps.io/mcp" &&
      azurerm_container_app.mcp.template[0].container[0].readiness_probe[0].path == "/health/ready" &&
      one([for env in azurerm_container_app.mcp.template[0].container[0].env : env.value if env.name == "MCP_API_CLIENT_ID"]) == var.api_client_id
    )
    error_message = "The auth audience and canonical resource URL must be explicit deployment values."
  }
}
run "no_mutable_image" {
  command = plan
  variables {
    image = "test.azurecr.io/newsloom-mcp:latest"
  }
  expect_failures = [var.image]
}
run "no_wildcard_origin" {
  command = plan
  variables {
    allowed_origins = ["https://*"]
  }
  expect_failures = [var.allowed_origins]
}
