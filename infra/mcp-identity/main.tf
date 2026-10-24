data "azuread_client_config" "current" {}

locals {
  prefix   = "newsloom-${var.environment_name}"
  scope_id = var.existing_scope_id != "" ? var.existing_scope_id : uuidv5("dns", "${local.prefix}/news.read")
}

resource "azuread_application" "api" {
  display_name     = "${local.prefix}-api"
  sign_in_audience = "AzureADMyOrg"
  owners           = [data.azuread_client_config.current.object_id]

  api {
    requested_access_token_version = 2
    oauth2_permission_scope {
      id                         = local.scope_id
      value                      = "news.read"
      type                       = "User"
      enabled                    = true
      admin_consent_display_name = "Read Newsloom news"
      admin_consent_description  = "Read stored enriched Newsloom news on behalf of the user."
      user_consent_display_name  = "Read Newsloom news"
      user_consent_description   = "Read stored enriched news using your organizational identity."
    }
  }
  lifecycle {
    prevent_destroy = true
    ignore_changes  = [identifier_uris]
  }
}

resource "azuread_application_identifier_uri" "api" {
  application_id = azuread_application.api.id
  identifier_uri = "api://${azuread_application.api.client_id}"
}

resource "azuread_application_identifier_uri" "mcp" {
  count          = var.resource_url == "" ? 0 : 1
  application_id = azuread_application.api.id
  identifier_uri = var.resource_url
  depends_on     = [azuread_application_identifier_uri.api]
}

resource "azuread_application" "client" {
  display_name                   = "${local.prefix}-vscode"
  sign_in_audience               = "AzureADMyOrg"
  owners                         = [data.azuread_client_config.current.object_id]
  fallback_public_client_enabled = true

  public_client {
    redirect_uris = var.redirect_uris
  }
  required_resource_access {
    resource_app_id = azuread_application.api.client_id
    resource_access {
      id   = local.scope_id
      type = "Scope"
    }
  }
  lifecycle {
    prevent_destroy = true
  }
}

resource "azuread_service_principal" "api" {
  client_id = azuread_application.api.client_id
  owners    = [data.azuread_client_config.current.object_id]
  lifecycle {
    prevent_destroy = true
  }
}

resource "azuread_service_principal" "client" {
  client_id = azuread_application.client.client_id
  owners    = [data.azuread_client_config.current.object_id]
  lifecycle {
    prevent_destroy = true
  }
}

import {
  for_each = var.existing_api_object_id == "" ? {} : { existing = var.existing_api_object_id }
  to       = azuread_application.api
  id       = "/applications/${each.value}"
}
import {
  for_each = var.existing_client_object_id == "" ? {} : { existing = var.existing_client_object_id }
  to       = azuread_application.client
  id       = "/applications/${each.value}"
}
import {
  for_each = var.existing_api_principal_id == "" ? {} : { existing = var.existing_api_principal_id }
  to       = azuread_service_principal.api
  id       = "/servicePrincipals/${each.value}"
}
import {
  for_each = var.existing_client_principal_id == "" ? {} : { existing = var.existing_client_principal_id }
  to       = azuread_service_principal.client
  id       = "/servicePrincipals/${each.value}"
}
import {
  for_each = var.existing_api_object_id == "" ? {} : { existing = var.existing_api_object_id }
  to       = azuread_application_identifier_uri.api
  id       = "/applications/${each.value}/identifierUris/${base64encode("api://${var.existing_api_client_id}")}"
}
import {
  for_each = var.existing_resource_identifier ? { existing = var.existing_api_object_id } : {}
  to       = azuread_application_identifier_uri.mcp[0]
  id       = "/applications/${each.value}/identifierUris/${base64encode(var.resource_url)}"
}

output "MCP_API_CLIENT_ID" {
  value = azuread_application.api.client_id
}
output "MCP_PUBLIC_CLIENT_ID" {
  value = azuread_application.client.client_id
}
output "MCP_NEWS_READ_SCOPE" {
  value = "api://${azuread_application.api.client_id}/news.read"
}
