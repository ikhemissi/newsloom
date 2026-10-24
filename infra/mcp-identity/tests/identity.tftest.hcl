mock_provider "azuread" {
  mock_data "azuread_client_config" {
    defaults = {
      object_id = join("-", ["00000000", "0000", "0000", "0000", "000000000001"])
      tenant_id = join("-", ["00000000", "0000", "0000", "0000", "000000000002"])
    }
  }
  mock_resource "azuread_application" {
    defaults = {
      id        = "/applications/${join("-", ["00000000", "0000", "0000", "0000", "000000000003"])}"
      client_id = join("-", ["00000000", "0000", "0000", "0000", "000000000004"])
      object_id = join("-", ["00000000", "0000", "0000", "0000", "000000000003"])
    }
  }
}
variables {
  tenant_id        = join("-", ["00000000", "0000", "0000", "0000", "000000000002"])
  environment_name = "test"
}

run "single_tenant_delegated_scope_and_public_client" {
  command = plan
  assert {
    condition = (
      azuread_application.api.sign_in_audience == "AzureADMyOrg" &&
      azuread_application.api.api[0].requested_access_token_version == 2 &&
      length(azuread_application.api.api[0].oauth2_permission_scope) == 1 &&
      one(azuread_application.api.api[0].oauth2_permission_scope).value == "news.read" &&
      one(azuread_application.api.api[0].oauth2_permission_scope).type == "User" &&
      azuread_application.client.sign_in_audience == "AzureADMyOrg" &&
      azuread_application.client.fallback_public_client_enabled &&
      azuread_application.client.public_client[0].redirect_uris == var.redirect_uris &&
      var.redirect_uris == toset([
        "http://localhost", "http://127.0.0.1:33418", "https://vscode.dev/redirect",
      ])
    )
    error_message = "Only single-tenant read scope and the approved pre-registered public client are supported."
  }
}
run "no_unapproved_callback" {
  command = plan
  variables {
    redirect_uris = ["https://attacker.invalid/callback"]
  }
  expect_failures = [var.redirect_uris]
}
run "no_ephemeral_port_registration" {
  command = plan
  variables {
    redirect_uris = ["http://localhost:53995"]
  }
  expect_failures = [var.redirect_uris]
}
run "no_lookalike_loopback" {
  command = plan
  variables {
    redirect_uris = ["http://localhost.attacker.invalid"]
  }
  expect_failures = [var.redirect_uris]
}
run "no_wildcard_callback" {
  command = plan
  variables {
    redirect_uris = ["http://localhost:*"]
  }
  expect_failures = [var.redirect_uris]
}
run "canonical_resource_alias_preserves_original_scope" {
  command = apply
  variables {
    resource_url = "https://newsloom.test/mcp"
  }
  assert {
    condition = (
      azuread_application_identifier_uri.mcp[0].identifier_uri == "https://newsloom.test/mcp" &&
      azuread_application_identifier_uri.api.identifier_uri == "api://${azuread_application.api.client_id}" &&
      one(azuread_application.api.api[0].oauth2_permission_scope).value == "news.read" &&
      azuread_application.api.api[0].requested_access_token_version == 2
    )
    error_message = "Add the exact resource alias to the same v2 API without replacing the existing URI or delegated scope."
  }
}
run "no_noncanonical_resource_alias" {
  command = plan
  variables {
    resource_url = "https://newsloom.test/mcp?extra=1"
  }
  expect_failures = [var.resource_url]
}
