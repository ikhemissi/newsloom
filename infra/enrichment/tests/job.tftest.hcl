mock_provider "azurerm" {}

variables {
  subscription_id              = join("-", ["00000000", "0000", "0000", "0000", "000000000000"])
  environment_name             = "test"
  location                     = "francecentral"
  resource_group_name          = "rg-newsloom-test"
  container_app_environment_id = "/subscriptions/${join("-", ["00000000", "0000", "0000", "0000", "000000000000"])}/resourceGroups/rg-newsloom-test/providers/Microsoft.App/managedEnvironments/test"
  registry_endpoint            = "test.azurecr.io"
  image                        = "test.azurecr.io/newsloom-enrichment@sha256:${join("", [for n in range(64) : "a"])}"
  workload_identities_base64 = base64encode(jsonencode({
    enrichment = {
      id        = "/subscriptions/${join("-", ["00000000", "0000", "0000", "0000", "000000000000"])}/resourceGroups/rg-newsloom-test/providers/Microsoft.ManagedIdentity/userAssignedIdentities/enrichment"
      client_id = join("-", ["00000000", "0000", "0000", "0000", "000000000001"])
    }
  }))
  postgres_host                         = "test.postgres.database.azure.com"
  postgres_database                     = "newsloom"
  model_endpoint                        = "https://test.services.ai.azure.com"
  generation_deployment                 = "generation"
  generation_model                      = "gpt-test"
  generation_version                    = "1"
  embedding_deployment                  = "embedding"
  embedding_model                       = "embedding-test"
  embedding_version                     = "1"
  applicationinsights_connection_string = "synthetic-routing-not-a-credential"
}

run "manual_first_with_existing_identity" {
  command = plan
  assert {
    condition = (
      length(azurerm_container_app_job.enrichment.manual_trigger_config) == 1 &&
      length(azurerm_container_app_job.enrichment.schedule_trigger_config) == 0 &&
      length(azurerm_container_app_job.enrichment.identity[0].identity_ids) == 1 &&
      azurerm_container_app_job.enrichment.replica_retry_limit == 0 &&
      azurerm_container_app_job.enrichment.template[0].container[0].image == var.image &&
      azurerm_container_app_job.enrichment.template[0].container[0].args == tolist(["run", "--limit", "25"]) &&
      azurerm_container_app_job.enrichment.registry[0].password_secret_name == null
    )
    error_message = "Start manual with an immutable image, capped real worker, and only its existing identity."
  }
}

run "approved_utc_schedule_and_own_model_config" {
  command = plan
  variables {
    schedule_enabled = true
  }
  assert {
    condition = (
      length(azurerm_container_app_job.enrichment.manual_trigger_config) == 0 &&
      azurerm_container_app_job.enrichment.schedule_trigger_config[0].cron_expression == "*/30 * * * *" &&
      one([for env in azurerm_container_app_job.enrichment.template[0].container[0].env : env.value if env.name == "ENRICHMENT_MODEL"]) == var.generation_model
    )
    error_message = "Use the reviewed UTC schedule and explicit owned model settings."
  }
}

run "no_mutable_image" {
  command = plan
  variables {
    image = "test.azurecr.io/newsloom-enrichment:latest"
  }
  expect_failures = [var.image]
}
