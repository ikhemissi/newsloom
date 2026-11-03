mock_provider "azurerm" {}

variables {
  subscription_id                       = join("-", ["00000000", "0000", "0000", "0000", "000000000000"])
  environment_name                      = "test"
  location                              = "francecentral"
  resource_group_name                   = "rg-newsloom-test"
  container_app_environment_id          = "/subscriptions/test/resourceGroups/test/providers/Microsoft.App/managedEnvironments/existing"
  registry_endpoint                     = "test.azurecr.io"
  postgres_host                         = "test.postgres.database.azure.com"
  postgres_database                     = "newsloom"
  model_endpoint                        = "https://test.services.ai.azure.com"
  generation_deployment                 = "briefing"
  generation_model                      = "existing-pinned-model"
  generation_version                    = "existing-pinned-version"
  applicationinsights_connection_string = "synthetic-routing-not-a-credential"
}

run "disabled_by_default" {
  command = plan
  assert {
    condition     = length(azurerm_container_app_job.briefing) == 0
    error_message = "The additive job is default off."
  }
}

run "manual_job_with_isolated_identity" {
  command = plan
  variables {
    enabled = true
    image   = "test.azurecr.io/newsloom-briefing@sha256:${join("", [for n in range(64) : "a"])}"
    identity_base64 = base64encode(jsonencode({
      id           = "/subscriptions/test/resourceGroups/test/providers/Microsoft.ManagedIdentity/userAssignedIdentities/briefing"
      client_id    = join("-", ["00000000", "0000", "0000", "0000", "000000000001"])
      principal_id = join("-", ["00000000", "0000", "0000", "0000", "000000000002"])
    }))
    input_price_per_million  = "0.1"
    output_price_per_million = "0.2"
    price_basis              = "2026-11-02 authored test fixture only"
  }
  assert {
    condition = (
      length(azurerm_container_app_job.briefing[0].manual_trigger_config) == 1 &&
      length(azurerm_container_app_job.briefing[0].schedule_trigger_config) == 0 &&
      azurerm_container_app_job.briefing[0].workload_profile_name == "Consumption" &&
      azurerm_container_app_job.briefing[0].replica_timeout_in_seconds == 3600 &&
      azurerm_container_app_job.briefing[0].replica_retry_limit == 0 &&
      azurerm_container_app_job.briefing[0].manual_trigger_config[0].parallelism == 1 &&
      azurerm_container_app_job.briefing[0].manual_trigger_config[0].replica_completion_count == 1 &&
      azurerm_container_app_job.briefing[0].template[0].container[0].args == tolist(["run"]) &&
      azurerm_container_app_job.briefing[0].template[0].container[0].image == var.image &&
      length(azurerm_container_app_job.briefing[0].identity[0].identity_ids) == 1 &&
      azurerm_container_app_job.briefing[0].registry[0].password_secret_name == null
    )
    error_message = "Manual bootstrap must use one Consumption replica, zero retries and 3600 seconds."
  }
  assert {
    condition = alltrue([
      for key, value in {
        BRIEFING_DEPLOYMENT               = var.generation_deployment
        BRIEFING_MODEL                    = var.generation_model
        BRIEFING_MODEL_VERSION            = var.generation_version
        BRIEFING_INPUT_PRICE_PER_MILLION  = var.input_price_per_million
        BRIEFING_OUTPUT_PRICE_PER_MILLION = var.output_price_per_million
        BRIEFING_PRICE_BASIS              = var.price_basis
      } : one([for e in azurerm_container_app_job.briefing[0].template[0].container[0].env : e.value if e.name == key]) == value
    ])
    error_message = "Pass the exact pinned model and explicit measurement inputs to the worker."
  }
}

run "daily_utc_schedule" {
  command = plan
  variables {
    enabled          = true
    schedule_enabled = true
    image            = "test.azurecr.io/newsloom-briefing@sha256:${join("", [for n in range(64) : "a"])}"
    identity_base64 = base64encode(jsonencode({
      id           = "/subscriptions/test/resourceGroups/test/providers/Microsoft.ManagedIdentity/userAssignedIdentities/briefing"
      client_id    = join("-", ["00000000", "0000", "0000", "0000", "000000000001"])
      principal_id = join("-", ["00000000", "0000", "0000", "0000", "000000000002"])
    }))
    input_price_per_million  = "0.1"
    output_price_per_million = "0.2"
    price_basis              = "2026-11-02 authored test fixture only"
  }
  assert {
    condition = (
      length(azurerm_container_app_job.briefing[0].manual_trigger_config) == 0 &&
      azurerm_container_app_job.briefing[0].schedule_trigger_config[0].cron_expression == "0 5 * * *" &&
      azurerm_container_app_job.briefing[0].schedule_trigger_config[0].parallelism == 1 &&
      azurerm_container_app_job.briefing[0].schedule_trigger_config[0].replica_completion_count == 1
    )
    error_message = "Daily scheduling is an explicit separate 05:00 UTC enablement."
  }
}

run "reject_schedule_without_workload" {
  command = plan
  variables {
    schedule_enabled = true
  }
  expect_failures = [var.schedule_enabled]
}

run "reject_mutable_image" {
  command = plan
  variables {
    enabled                  = true
    image                    = "test.azurecr.io/newsloom-briefing:latest"
    identity_base64          = base64encode(jsonencode({ id = "test", client_id = "test", principal_id = "test" }))
    input_price_per_million  = "0.1"
    output_price_per_million = "0.2"
    price_basis              = "2026-11-02 test"
  }
  expect_failures = [var.image]
}
