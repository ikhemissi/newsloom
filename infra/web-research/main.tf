locals {
  name = "webiq-newsloom-${var.environment_name}"
}

# Web IQ account that meters web searches. The agent authenticates with its
# managed identity, whose client ID is bound to this account's AppID in Web IQ
# profiles (a manual step; see docs/agent.md). No key is created or stored.
resource "azapi_resource" "webiq" {
  count     = var.enabled ? 1 : 0
  type      = "Microsoft.WebIQ/accounts@2026-06-01-preview"
  name      = local.name
  parent_id = "/subscriptions/${var.subscription_id}/resourceGroups/${var.resource_group_name}"
  location  = "global"
  tags      = merge(var.tags, { azd-env-name = var.environment_name })
  body = {
    kind = "WebIQ.Grounding"
    sku  = { name = "G3" }
  }
  schema_validation_enabled = false
  response_export_values    = ["properties.provisioningState"]
}

output "WEBIQ_ACCOUNT_NAME" {
  value = var.enabled ? azapi_resource.webiq[0].name : ""
}
