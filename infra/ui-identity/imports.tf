import {
  for_each = var.enabled && var.adoption.client_object_id != "" ? { existing = var.adoption.client_object_id } : {}
  to       = azuread_application.client[0]
  id       = "/applications/${each.value}"
}
import {
  for_each = var.enabled && var.adoption.client_principal_id != "" ? { existing = var.adoption.client_principal_id } : {}
  to       = azuread_service_principal.client[0]
  id       = "/servicePrincipals/${each.value}"
}
import {
  for_each = var.enabled && var.consent_enabled && var.adoption.consent_id != "" ? { existing = var.adoption.consent_id } : {}
  to       = azuread_service_principal_delegated_permission_grant.agent[0]
  id       = "/oauth2PermissionGrants/${each.value}"
}
import {
  for_each = var.news_enabled && var.consent_enabled && var.existing_mcp_consent_id != "" ? { existing = var.existing_mcp_consent_id } : {}
  to       = azuread_service_principal_delegated_permission_grant.mcp[0]
  id       = "/oauth2PermissionGrants/${each.value}"
}
