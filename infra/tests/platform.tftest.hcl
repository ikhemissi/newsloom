mock_provider "azurerm" {
  mock_data "azurerm_client_config" {
    defaults = {
      tenant_id = join("-", ["00000000", "0000", "0000", "0000", "000000000000"])
    }
  }
}

variables {
  subscription_id      = join("-", ["00000000", "0000", "0000", "0000", "000000000000"])
  environment_name     = "test"
  location             = "francecentral"
  resource_group_name  = "rg-newsloom-test"
  postgres_sku         = "B_Standard_B1ms"
  postgres_storage_mb  = 32768
  postgres_backup_days = 7
  log_retention_days   = 30
  log_daily_cap_gb     = 0.1
  models = {
    enrichment = {
      deployment_name = "enrichment"
      name            = "gpt-5.4-mini"
      version         = "2026-03-17"
      format          = "OpenAI"
      sku             = "DataZoneStandard"
      capacity        = 10
    }
    embeddings = {
      deployment_name = "embeddings"
      name            = "text-embedding-3-large"
      version         = "1"
      format          = "OpenAI"
      sku             = "Standard"
      capacity        = 10
    }
    screening = {
      deployment_name = "screening"
      name            = "Microsoft-Decision-1"
      version         = "1"
      format          = "Microsoft"
      sku             = "DataZoneStandard"
      capacity        = 60
    }
  }
}

run "secretless_platform_configuration" {
  command = plan

  assert {
    condition = (
      !azurerm_container_registry.application.admin_enabled &&
      !azurerm_cognitive_account.models.local_auth_enabled &&
      !azurerm_application_insights.application.local_authentication_enabled &&
      !azurerm_log_analytics_workspace.application.local_authentication_enabled &&
      azurerm_postgresql_flexible_server.application.authentication[0].active_directory_auth_enabled &&
      !azurerm_postgresql_flexible_server.application.authentication[0].password_auth_enabled
    )
    error_message = "Platform services must not enable password or shared-key access."
  }

  assert {
    condition = (
      azurerm_postgresql_flexible_server.application.version == "18" &&
      azurerm_postgresql_flexible_server_configuration.extensions.value == "VECTOR" &&
      azurerm_postgresql_flexible_server_firewall_rule.azure_services.start_ip_address == "0.0.0.0" &&
      azurerm_postgresql_flexible_server_firewall_rule.azure_services.end_ip_address == "0.0.0.0" &&
      azurerm_postgresql_flexible_server_active_directory_administrator.migrations.principal_type == "ServicePrincipal" &&
      length(azurerm_user_assigned_identity.workload) == 4
    )
    error_message = "Use PostgreSQL 18/vector and only the documented Azure-services exception with separate identities."
  }

  assert {
    condition = (
      azurerm_container_app_environment.application.logs_destination == "azure-monitor" &&
      azurerm_container_app_environment.application.log_analytics_workspace_id == null &&
      azurerm_role_assignment.registry_pull["migrations"].role_definition_name == "AcrPull" &&
      length(azurerm_role_assignment.telemetry) == 3
    )
    error_message = "Diagnostics must avoid shared keys and the migration identity must not receive runtime telemetry grants."
  }

  assert {
    condition = (
      toset(azurerm_role_definition.inference["mcp"].permissions[0].data_actions) ==
      toset(["Microsoft.CognitiveServices/accounts/OpenAI/deployments/embeddings/action"]) &&
      toset(azurerm_role_definition.inference["ingestion"].permissions[0].data_actions) ==
      toset(["Microsoft.CognitiveServices/accounts/AIServices/providers/action"]) &&
      length(azurerm_role_definition.inference["enrichment"].permissions[0].data_actions) == 2 &&
      alltrue([for role in azurerm_role_definition.inference : length(role.permissions[0].actions) == 0])
    )
    error_message = "Inference grants must be explicit API operations without management actions."
  }

  assert {
    condition = alltrue([
      for model in azurerm_cognitive_deployment.model : model.version_upgrade_option == "NoAutoUpgrade"
    ])
    error_message = "Pinned model versions must not silently auto-upgrade."
  }

  assert {
    condition = (
      azurerm_cognitive_account.models.project_management_enabled &&
      azurerm_cognitive_account.models.identity[0].type == "SystemAssigned" &&
      azurerm_cognitive_account.models.name == "ai-newsloom-test-${substr(sha256("${var.subscription_id}/test"), 0, 8)}" &&
      azurerm_cognitive_account.models.custom_subdomain_name == azurerm_cognitive_account.models.name &&
      length(azurerm_cognitive_deployment.model) == 3 &&
      length(azurerm_role_assignment.inference) == 3 &&
      length(azurerm_role_assignment.registry_pull) == 4 &&
      azurerm_cognitive_deployment.model["enrichment"].model[0].name == var.models.enrichment.name &&
      azurerm_cognitive_deployment.model["enrichment"].model[0].version == var.models.enrichment.version &&
      azurerm_cognitive_deployment.model["enrichment"].sku[0].capacity == var.models.enrichment.capacity
    )
    error_message = "Enable only lasting account prerequisites; preserve the account name, all models and workload grants."
  }
}

run "reject_missing_model_contracts" {
  command = plan

  variables {
    models = {}
  }

  expect_failures = [var.models]
}

run "reject_unmetered_or_invalid_model_settings" {
  command = plan

  variables {
    models = {
      for key, model in var.models : key => merge(model, { capacity = 0, sku = "ProvisionedManaged" })
    }
  }

  expect_failures = [var.models]
}
