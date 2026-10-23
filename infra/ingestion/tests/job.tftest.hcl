mock_provider "azurerm" {}

variables {
  subscription_id              = join("-", ["00000000", "0000", "0000", "0000", "000000000000"])
  environment_name             = "test"
  location                     = "francecentral"
  resource_group_name          = "rg-newsloom-test"
  container_app_environment_id = "/subscriptions/${join("-", ["00000000", "0000", "0000", "0000", "000000000000"])}/resourceGroups/rg-newsloom-test/providers/Microsoft.App/managedEnvironments/test"
  registry_endpoint            = "test.azurecr.io"
  image                        = "test.azurecr.io/newsloom-ingestion@sha256:${join("", [for n in range(64) : "a"])}"
  workload_identities_base64 = base64encode(jsonencode({
    ingestion = {
      id        = "/subscriptions/${join("-", ["00000000", "0000", "0000", "0000", "000000000000"])}/resourceGroups/rg-newsloom-test/providers/Microsoft.ManagedIdentity/userAssignedIdentities/ingestion"
      client_id = join("-", ["00000000", "0000", "0000", "0000", "000000000001"])
    }
  }))
  postgres_host                         = "test.postgres.database.azure.com"
  postgres_database                     = "newsloom"
  model_endpoint                        = "https://test.services.ai.azure.com"
  screening_deployment                  = "screening"
  applicationinsights_connection_string = "synthetic-routing-not-a-credential"
}

run "initial_job_is_manual_and_uses_existing_identity" {
  command = plan
  assert {
    condition = (
      length(azurerm_container_app_job.ingestion.manual_trigger_config) == 1 &&
      length(azurerm_container_app_job.ingestion.schedule_trigger_config) == 0 &&
      length(azurerm_container_app_job.ingestion.identity[0].identity_ids) == 1 &&
      azurerm_container_app_job.ingestion.template[0].container[0].image == var.image &&
      azurerm_container_app_job.ingestion.replica_retry_limit == 0 &&
      azurerm_container_app_job.ingestion.registry[0].password_secret_name == null
    )
    error_message = "Initial acceptance must use the real manually started, identity-authenticated job."
  }
}

run "approved_utc_schedule" {
  command = plan
  variables {
    schedule_enabled    = true
    screening_threshold = "0.5"
  }
  assert {
    condition = (
      length(azurerm_container_app_job.ingestion.manual_trigger_config) == 0 &&
      azurerm_container_app_job.ingestion.schedule_trigger_config[0].cron_expression == "*/30 * * * *"
    )
    error_message = "Only the approved UTC schedule is supported."
  }
}

run "no_schedule_without_calibration" {
  command = plan
  variables {
    schedule_enabled = true
  }
  expect_failures = [azurerm_container_app_job.ingestion]
}

run "no_mutable_image" {
  command = plan
  variables {
    image = "test.azurecr.io/newsloom-ingestion:latest"
  }
  expect_failures = [var.image]
}
