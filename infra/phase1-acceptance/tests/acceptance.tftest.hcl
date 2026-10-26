mock_provider "azurerm" {
  mock_data "azurerm_container_app_environment" {
    defaults = {
      id             = "/subscriptions/${join("-", ["00000000", "0000", "0000", "0000", "000000000000"])}/resourceGroups/rg-newsloom-test/providers/Microsoft.App/managedEnvironments/cae-newsloom-test"
      default_domain = "synthetic-environment.francecentral.azurecontainerapps.io"
    }
  }
  mock_data "azurerm_log_analytics_workspace" {
    defaults = {
      id = "/subscriptions/${join("-", ["00000000", "0000", "0000", "0000", "000000000000"])}/resourceGroups/rg-newsloom-test/providers/Microsoft.OperationalInsights/workspaces/log-newsloom-test"
    }
  }
}

variables {
  subscription_id                       = join("-", ["00000000", "0000", "0000", "0000", "000000000000"])
  environment_name                      = "test"
  resource_group_name                   = "rg-newsloom-test"
  location                              = "francecentral"
  container_app_environment_id          = "/subscriptions/${join("-", ["00000000", "0000", "0000", "0000", "000000000000"])}/resourceGroups/rg-newsloom-test/providers/Microsoft.App/managedEnvironments/cae-newsloom-test"
  registry_id                           = "/subscriptions/${join("-", ["00000000", "0000", "0000", "0000", "000000000000"])}/resourceGroups/rg-newsloom-test/providers/Microsoft.ContainerRegistry/registries/test"
  registry_endpoint                     = "test.azurecr.io"
  model_account_id                      = "/subscriptions/${join("-", ["00000000", "0000", "0000", "0000", "000000000000"])}/resourceGroups/rg-newsloom-test/providers/Microsoft.CognitiveServices/accounts/test"
  applicationinsights_id                = "/subscriptions/${join("-", ["00000000", "0000", "0000", "0000", "000000000000"])}/resourceGroups/rg-newsloom-test/providers/Microsoft.Insights/components/test"
  applicationinsights_connection_string = "synthetic-not-a-credential"
  test_settings = {
    postgres_host          = "test.postgres.database.azure.com"
    model_endpoint         = "https://test.services.ai.azure.com"
    generation_deployment  = "generation"
    generation_model       = "gpt-5.4-mini"
    generation_version     = "1"
    embedding_deployment   = "embedding"
    embedding_model        = "text-embedding-3-large"
    embedding_version      = "1"
    screening_deployment   = "screening"
    screening_model        = "Microsoft-Decision-1"
    screening_version      = "1"
    scanner_threshold      = 0.5
    scanner_calibration_id = join("", [for n in range(64) : "a"])
  }
}

run "disabled_by_default_creates_nothing" {
  command = plan
  assert {
    condition = (
      length(azurerm_user_assigned_identity.acceptance) == 0 &&
      length(azurerm_container_app_job.acceptance) == 0 &&
      length(azurerm_federated_identity_credential.github) == 0 &&
      length(azurerm_role_assignment.control) == 0 &&
      length(azurerm_role_assignment.log_reader) == 0 &&
      length(data.azurerm_log_analytics_workspace.application) == 0 &&
      length(data.azurerm_container_app_environment.application) == 0
    )
    error_message = "Acceptance is opt-in and cannot add resources by default."
  }
}

run "manual_finite_job_and_exact_federation" {
  command = plan
  variables {
    enabled        = true
    image          = "test.azurecr.io/newsloom-phase1@sha256:${join("", [for n in range(64) : "a"])}"
    image_revision = join("", [for n in range(64) : "b"])
  }
  assert {
    condition = (
      length(azurerm_container_app_job.acceptance[0].manual_trigger_config) == 1 &&
      length(azurerm_container_app_job.acceptance[0].schedule_trigger_config) == 0 &&
      azurerm_container_app_job.acceptance[0].replica_retry_limit == 0 &&
      azurerm_container_app_job.acceptance[0].replica_timeout_in_seconds == 1200 &&
      azurerm_container_app_job.acceptance[0].template[0].container[0].cpu == 0.25 &&
      azurerm_container_app_job.acceptance[0].template[0].container[0].memory == "0.5Gi" &&
      azurerm_federated_identity_credential.github[0].subject == "repo:ikhemissi@1769608/newsloom@1429962749:ref:refs/heads/main" &&
      azurerm_federated_identity_credential.github[0].issuer == "https://token.actions.githubusercontent.com" &&
      length(azurerm_federated_identity_credential.github[0].audience) == 1 &&
      one(azurerm_federated_identity_credential.github[0].audience) == "api://AzureADTokenExchange"
    )
    error_message = "Use only the exact manually approved OIDC subject and finite manual test job."
  }
  assert {
    condition = (
      length(azurerm_role_definition.inference[0].permissions[0].data_actions) == 3 &&
      toset(azurerm_role_definition.control[0].permissions[0].actions) == toset([
        "Microsoft.App/jobs/read",
        "Microsoft.App/jobs/start/action",
        "Microsoft.App/jobs/stop/action",
        "Microsoft.App/jobs/execution/read",
        "Microsoft.App/jobs/executions/read",
      ]) &&
      length(azurerm_role_definition.control[0].permissions[0].data_actions) == 0 &&
      azurerm_role_assignment.registry[0].role_definition_name == "AcrPull" &&
      azurerm_role_assignment.telemetry[0].role_definition_name == "Monitoring Metrics Publisher"
    )
    error_message = "No broad management, registry push, keys or production identity grants are permitted."
  }
  assert {
    condition = (
      azurerm_role_assignment.log_reader[0].role_definition_name == "Log Analytics Data Reader" &&
      azurerm_role_assignment.log_reader[0].scope == data.azurerm_log_analytics_workspace.application[0].id &&
      data.azurerm_log_analytics_workspace.application[0].name == "log-newsloom-test" &&
      data.azurerm_container_app_environment.application[0].name == "cae-newsloom-test" &&
      azurerm_role_assignment.log_reader[0].condition_version == "2.0" &&
      trimspace(azurerm_role_assignment.log_reader[0].condition) == trimspace(<<-EOT
        (
          !(ActionMatches{'Microsoft.OperationalInsights/workspaces/tables/data/read'})
          OR
          (
            @Resource[Microsoft.OperationalInsights/workspaces/tables:name] StringEquals 'ContainerAppConsoleLogs'
            AND
            @Resource[Microsoft.OperationalInsights/workspaces/tables/record:JobName<$key_case_sensitive$>] StringEquals 'accept-newsloom-test'
            AND
            @Resource[Microsoft.OperationalInsights/workspaces/tables/record:EnvironmentName<$key_case_sensitive$>] StringEquals 'synthetic-environment'
          )
        )
      EOT
      )
    )
    error_message = "Log access requires an exact generated table/job/environment condition at the existing workspace."
  }
}

run "no_mutable_image" {
  command = plan
  variables {
    enabled        = true
    image          = "test.azurecr.io/newsloom-phase1:latest"
    image_revision = join("", [for n in range(64) : "a"])
  }
  expect_failures = [var.image]
}

run "no_foreign_repository_trust" {
  command = plan
  variables {
    github_subject = "repo:unapproved@1769608/fork@1429962749:ref:refs/heads/main"
  }
  expect_failures = [var.github_subject]
}
run "no_environment_subject" {
  command = plan
  variables {
    github_subject = "repo:ikhemissi@1769608/newsloom@1429962749:environment:phase1-acceptance"
  }
  expect_failures = [var.github_subject]
}
run "no_other_ref" {
  command = plan
  variables {
    github_subject = "repo:ikhemissi@1769608/newsloom@1429962749:ref:refs/heads/unapproved"
  }
  expect_failures = [var.github_subject]
}
run "no_legacy_name_only_subject" {
  command = plan
  variables {
    github_subject = "repo:ikhemissi/newsloom:ref:refs/heads/main"
  }
  expect_failures = [var.github_subject]
}
run "no_foreign_owner_id" {
  command = plan
  variables {
    github_subject = "repo:ikhemissi@1/newsloom@1429962749:ref:refs/heads/main"
  }
  expect_failures = [var.github_subject]
}
run "no_foreign_repository_id" {
  command = plan
  variables {
    github_subject = "repo:ikhemissi@1769608/newsloom@1:ref:refs/heads/main"
  }
  expect_failures = [var.github_subject]
}
run "no_log_condition_injection" {
  command = plan
  variables {
    environment_name = "test' OR 'foreign"
  }
  expect_failures = [var.environment_name]
}
run "no_foreign_log_environment" {
  command = plan
  variables {
    container_app_environment_id = "/subscriptions/${join("-", ["00000000", "0000", "0000", "0000", "000000000000"])}/resourceGroups/rg-newsloom-test/providers/Microsoft.App/managedEnvironments/foreign"
  }
  expect_failures = [var.container_app_environment_id]
}

run "no_foreign_log_environment_metadata" {
  command = plan
  variables {
    enabled        = true
    image          = "test.azurecr.io/newsloom-phase1@sha256:${join("", [for n in range(64) : "a"])}"
    image_revision = join("", [for n in range(64) : "b"])
  }
  override_data {
    target = data.azurerm_container_app_environment.application[0]
    values = {
      id             = "/subscriptions/${join("-", ["00000000", "0000", "0000", "0000", "000000000000"])}/resourceGroups/rg-newsloom-test/providers/Microsoft.App/managedEnvironments/cae-newsloom-foreign"
      default_domain = "foreign-environment.francecentral.azurecontainerapps.io"
    }
  }
  expect_failures = [data.azurerm_container_app_environment.application[0]]
}
