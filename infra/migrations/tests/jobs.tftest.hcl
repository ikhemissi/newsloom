mock_provider "azurerm" {}

variables {
  subscription_id              = join("-", ["00000000", "0000", "0000", "0000", "000000000000"])
  environment_name             = "test"
  location                     = "francecentral"
  resource_group_name          = "rg-newsloom-test"
  container_app_environment_id = "/subscriptions/${join("-", ["00000000", "0000", "0000", "0000", "000000000000"])}/resourceGroups/rg-newsloom-test/providers/Microsoft.App/managedEnvironments/test"
  registry_endpoint            = "test.azurecr.io"
  image                        = "test.azurecr.io/newsloom-platform@sha256:${join("", [for n in range(64) : "a"])}"
  workload_identities_base64 = base64encode(jsonencode({
    for index, name in ["ingestion", "enrichment", "mcp", "migrations"] : name => {
      id           = "/subscriptions/${join("-", ["00000000", "0000", "0000", "0000", "000000000000"])}/resourceGroups/rg-newsloom-test/providers/Microsoft.ManagedIdentity/userAssignedIdentities/${name}"
      client_id    = join("-", ["00000000", "0000", "0000", "0000", format("%012d", index + 1)])
      principal_id = join("-", ["00000000", "0000", "0000", "0000", format("%012d", index + 101)])
    }
  }))
  postgres_host                         = "test.postgres.database.azure.com"
  postgres_database                     = "newsloom"
  postgres_admin_name                   = "migrations"
  model_endpoint                        = "https://test.services.ai.azure.com"
  model_account_id                      = "/subscriptions/${join("-", ["00000000", "0000", "0000", "0000", "000000000000"])}/resourceGroups/rg-newsloom-test/providers/Microsoft.CognitiveServices/accounts/test"
  enrichment_deployment                 = "enrichment"
  embeddings_deployment                 = "embeddings"
  screening_deployment                  = "screening"
  applicationinsights_connection_string = "synthetic-routing-not-a-credential"
  verification_enabled                  = true
}

run "jobs_use_one_identity_and_real_immutable_image" {
  command = plan

  assert {
    condition = (
      length(azurerm_container_app_job.operation) == 5 &&
      alltrue([
        for key, job in azurerm_container_app_job.operation :
        length(job.identity[0].identity_ids) == 1 &&
        job.template[0].container[0].image == var.image &&
        job.replica_retry_limit == 0 &&
        job.manual_trigger_config[0].replica_completion_count == 1 &&
        job.registry[0].password_secret_name == null &&
        job.registry[0].username == null
      ])
    )
    error_message = "Each real manual job must have one identity, managed registry pull, an immutable image, and visible terminal failure."
  }

  assert {
    condition = (
      azurerm_container_app_job.operation["migrate"].template[0].container[0].args == tolist(["migrate"]) &&
      alltrue([
        for key, job in azurerm_container_app_job.operation :
        length(job.name) <= 32
      ])
    )
    error_message = "Initialization must use the actual migration command and valid job names."
  }
}

run "cleanup_keeps_only_the_migration_job" {
  command = plan

  variables {
    verification_enabled = false
  }

  assert {
    condition     = toset(keys(azurerm_container_app_job.operation)) == toset(["migrate"])
    error_message = "Disabling verification must retain initialization and own no shared resources."
  }
}

run "reject_placeholder_image" {
  command = plan

  variables {
    image = "test.azurecr.io/newsloom-platform:latest"
  }

  expect_failures = [var.image]
}
