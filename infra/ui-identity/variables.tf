variable "enabled" {
  type    = bool
  default = false
}
variable "consent_enabled" {
  type    = bool
  default = false
}
variable "news_enabled" {
  type    = bool
  default = false
  validation {
    condition     = !var.news_enabled || var.enabled
    error_message = "Browser news requires the explicitly enabled existing UI."
  }
}
variable "mcp_api_client_id" {
  type    = string
  default = ""
}
variable "mcp_api_principal_id" {
  type    = string
  default = ""
}
variable "mcp_scope_id" {
  type    = string
  default = ""
}
variable "existing_mcp_consent_id" {
  type    = string
  default = ""
  validation {
    condition     = var.existing_mcp_consent_id == "" || can(regex("^[A-Za-z0-9_-]{1,128}$", var.existing_mcp_consent_id))
    error_message = "Adopt only the exact scoped MCP consent ID."
  }
}
variable "tenant_id" {
  type = string
}
variable "subscription_id" {
  type = string
}
variable "environment_name" {
  type = string
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{0,40}$", var.environment_name))
    error_message = "Use the retained environment's safe name."
  }
}
variable "resource_group_name" {
  type = string
}
variable "container_app_environment_id" {
  type = string
  validation {
    condition     = !var.enabled || var.container_app_environment_id == "/subscriptions/${var.subscription_id}/resourceGroups/${var.resource_group_name}/providers/Microsoft.App/managedEnvironments/cae-newsloom-${var.environment_name}"
    error_message = "The SPA must use the retained ACA environment's domain."
  }
}
variable "agent_api_client_id" {
  type = string
}
variable "agent_api_principal_id" {
  type = string
}
variable "agent_scope_id" {
  type = string
}
variable "adoption" {
  type = object({
    client_object_id    = string
    client_client_id    = string
    client_principal_id = string
    consent_id          = string
  })
  default = {
    client_object_id = "", client_client_id = "", client_principal_id = "", consent_id = ""
  }
  validation {
    condition = alltrue([for key, value in var.adoption : value == "" || (
      key == "consent_id" ? can(regex("^[A-Za-z0-9_-]{1,128}$", value)) :
      can(regex("^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$", value))
    )]) && ((var.adoption.client_object_id == "") == (var.adoption.client_client_id == ""))
    error_message = "Adopt only coherent exact SPA object/client/principal/consent IDs."
  }
}
