mock_provider "azurerm" {}

variables {
  subscription_id              = join("-", ["00000000", "0000", "0000", "0000", "000000000000"])
  environment_name             = "test"
  resource_group_name          = "rg-newsloom-test"
  location                     = "francecentral"
  container_app_environment_id = "/subscriptions/test/resourceGroups/test/providers/Microsoft.App/managedEnvironments/existing"
  registry_endpoint            = "existing.azurecr.io"
  identity_base64 = base64encode(jsonencode({
    id           = "/subscriptions/test/resourceGroups/test/providers/Microsoft.ManagedIdentity/userAssignedIdentities/id-newsloom-test-operations"
    client_id    = join("-", ["00000000", "0000", "0000", "0000", "000000000002"])
    principal_id = join("-", ["00000000", "0000", "0000", "0000", "000000000003"])
  }))
  image                = "existing.azurecr.io/newsloom-operations@sha256:${join("", [for i in range(64) : "a"])}"
  postgres_host        = "psql-newsloom-test.postgres.database.azure.com"
  postgres_database    = "newsloom"
  postgres_server_name = "psql-newsloom-test"
  backup_account_url   = "https://stnlbaktest.blob.core.windows.net/"
  backup_container     = "postgres"
}

run "nightly_export_then_stop_and_morning_wake" {
  command = plan
  assert {
    condition = (
      azurerm_container_app_job.operations["nightly"].schedule_trigger_config[0].cron_expression == "0 23 * * *" &&
      azurerm_container_app_job.operations["nightly"].template[0].container[0].args == tolist(["nightly"]) &&
      azurerm_container_app_job.operations["nightly"].replica_timeout_in_seconds == 3600 &&
      azurerm_container_app_job.operations["wake"].schedule_trigger_config[0].cron_expression == "0 7 * * *" &&
      azurerm_container_app_job.operations["wake"].template[0].container[0].args == tolist(["wake"]) &&
      azurerm_container_app_job.operations["wake"].replica_retry_limit == 0 &&
      length(azurerm_container_app_job.operations["nightly"].name) <= 32 &&
      length(azurerm_container_app_job.operations["backup"].schedule_trigger_config) == 0 &&
      length(azurerm_container_app_job.operations["backup"].manual_trigger_config) == 1 &&
      azurerm_container_app_job.operations["backup"].template[0].container[0].args == tolist(["backup"])
    )
    error_message = "The export and stop run at 23:00 UTC; the wake at 07:00 UTC."
  }
}

run "jobs_use_only_the_operations_identity_and_no_secrets" {
  command = plan
  assert {
    condition = alltrue([
      for job in azurerm_container_app_job.operations : (
        job.identity[0].identity_ids == toset(["/subscriptions/test/resourceGroups/test/providers/Microsoft.ManagedIdentity/userAssignedIdentities/id-newsloom-test-operations"]) &&
        length(job.secret) == 0 &&
        alltrue([for env in job.template[0].container[0].env : env.secret_name == null || env.secret_name == ""])
      )
    ])
    error_message = "Operations jobs authenticate only with their managed identity."
  }
}

run "manual_trigger_when_schedule_disabled" {
  command = plan
  variables {
    schedule_enabled = false
  }
  assert {
    condition     = alltrue([for job in azurerm_container_app_job.operations : length(job.schedule_trigger_config) == 0 && length(job.manual_trigger_config) == 1])
    error_message = "Schedules can be disabled for manual runs."
  }
}

run "mutable_images_are_rejected" {
  command = plan
  variables {
    image = "existing.azurecr.io/newsloom-operations:latest"
  }
  expect_failures = [var.image]
}
