import {
  for_each = var.enabled && var.adoption.api_object_id != "" ? { existing = var.adoption.api_object_id } : {}
  to       = azuread_application.api[0]
  id       = "/applications/${each.value}"
}
import {
  for_each = var.enabled && var.adoption.client_object_id != "" ? { existing = var.adoption.client_object_id } : {}
  to       = azuread_application.client[0]
  id       = "/applications/${each.value}"
}
import {
  for_each = var.enabled && var.adoption.api_principal_id != "" ? { existing = var.adoption.api_principal_id } : {}
  to       = azuread_service_principal.api[0]
  id       = "/servicePrincipals/${each.value}"
}
import {
  for_each = var.enabled && var.adoption.client_principal_id != "" ? { existing = var.adoption.client_principal_id } : {}
  to       = azuread_service_principal.client[0]
  id       = "/servicePrincipals/${each.value}"
}
import {
  for_each = var.enabled && var.adoption.api_object_id != "" ? { existing = var.adoption.api_object_id } : {}
  to       = azuread_application_identifier_uri.api[0]
  id       = "/applications/${each.value}/identifierUris/${base64encode("api://${var.adoption.api_client_id}")}"
}
import {
  for_each = var.enabled && var.adoption.federation_id != "" ? { existing = var.adoption.federation_id } : {}
  to       = azuread_application_federated_identity_credential.managed_identity[0]
  id       = "/applications/${var.adoption.api_object_id}/federatedIdentityCredentials/${each.value}"
}
import {
  for_each = var.enabled && var.consent_enabled && var.adoption.mcp_consent_id != "" ? { existing = var.adoption.mcp_consent_id } : {}
  to       = azuread_service_principal_delegated_permission_grant.mcp[0]
  id       = "/oauth2PermissionGrants/${each.value}"
}
import {
  for_each = var.enabled && var.consent_enabled && var.adoption.client_consent_id != "" ? { existing = var.adoption.client_consent_id } : {}
  to       = azuread_service_principal_delegated_permission_grant.client[0]
  id       = "/oauth2PermissionGrants/${each.value}"
}
