variable "enabled" {
  type    = bool
  default = false
}
variable "consent_enabled" {
  type    = bool
  default = false
}
variable "tenant_id" {
  type = string
  validation {
    condition     = !var.enabled || can(regex("^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$", var.tenant_id))
    error_message = "Use the configured single tenant's UUID."
  }
}
variable "subscription_id" {
  type = string
}
variable "environment_name" {
  type = string
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{0,40}$", var.environment_name))
    error_message = "Use the retained environment's safe resource-name suffix."
  }
}
variable "resource_group_name" {
  type = string
}
variable "location" {
  type = string
}
variable "registry_id" {
  type = string
  validation {
    condition     = !var.enabled || var.registry_id == "/subscriptions/${var.subscription_id}/resourceGroups/${var.resource_group_name}/providers/Microsoft.ContainerRegistry/registries/acrnewsloom${replace(var.environment_name, "-", "")}${substr(sha256("${var.subscription_id}/${var.environment_name}"), 0, 8)}"
    error_message = "Use the existing owning registry, not another resource or broader scope."
  }
}
variable "model_account_id" {
  type = string
  validation {
    condition     = !var.enabled || var.model_account_id == "/subscriptions/${var.subscription_id}/resourceGroups/${var.resource_group_name}/providers/Microsoft.CognitiveServices/accounts/ai-newsloom-${var.environment_name}-${substr(sha256("${var.subscription_id}/${var.environment_name}"), 0, 8)}"
    error_message = "Use the existing owning Foundry account without changing deployments or capacity."
  }
}
variable "applicationinsights_id" {
  type = string
  validation {
    condition     = !var.enabled || var.applicationinsights_id == "/subscriptions/${var.subscription_id}/resourceGroups/${var.resource_group_name}/providers/Microsoft.Insights/components/appi-newsloom-${var.environment_name}"
    error_message = "Use the existing authenticated telemetry component."
  }
}
variable "mcp_api_client_id" {
  type    = string
  default = ""
  validation {
    condition     = !var.enabled || can(regex("^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$", var.mcp_api_client_id))
    error_message = "Enabled agent identity requires the exact inventoried MCP API client ID."
  }
}
variable "mcp_api_principal_id" {
  type    = string
  default = ""
  validation {
    condition     = !var.enabled || can(regex("^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$", var.mcp_api_principal_id))
    error_message = "Use the existing same-tenant MCP service principal's object ID."
  }
}
variable "mcp_scope_id" {
  type    = string
  default = ""
  validation {
    condition     = !var.enabled || can(regex("^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$", var.mcp_scope_id))
    error_message = "Use only the existing inventoried news.read delegated scope ID."
  }
}
variable "redirect_uris" {
  type    = set(string)
  default = ["http://127.0.0.1:8400/callback"]
  validation {
    condition     = var.redirect_uris == toset(["http://127.0.0.1:8400/callback"])
    error_message = "Only the separate acceptance client's exact IPv4 loopback callback is supported."
  }
}
variable "adoption" {
  type = object({
    api_object_id       = string
    api_client_id       = string
    api_principal_id    = string
    scope_id            = string
    client_object_id    = string
    client_client_id    = string
    client_principal_id = string
    federation_id       = string
    mcp_consent_id      = string
    client_consent_id   = string
  })
  default = {
    api_object_id       = ""
    api_client_id       = ""
    api_principal_id    = ""
    scope_id            = ""
    client_object_id    = ""
    client_client_id    = ""
    client_principal_id = ""
    federation_id       = ""
    mcp_consent_id      = ""
    client_consent_id   = ""
  }
  validation {
    condition = alltrue([
      for key, value in var.adoption :
      value == "" || (
        contains(["mcp_consent_id", "client_consent_id"], key) ?
        can(regex("^[A-Za-z0-9_-]{1,128}$", value)) :
        can(regex("^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$", value))
      )
    ])
    error_message = "Adoption accepts only exact UUIDs or opaque consent IDs, never names, URLs or wildcards."
  }
  validation {
    condition = (
      (var.adoption.api_object_id == "") == (var.adoption.api_client_id == "") &&
      (var.adoption.api_object_id == "") == (var.adoption.scope_id == "") &&
      (var.adoption.client_object_id == "") == (var.adoption.client_client_id == "")
    )
    error_message = "Adoption requires a coherent exact application/client/scope inventory."
  }
}
variable "tags" {
  type    = map(string)
  default = {}
}
