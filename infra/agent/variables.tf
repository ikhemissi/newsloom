variable "enabled" {
  type    = bool
  default = false
}
variable "subscription_id" {
  type = string
}
variable "tenant_id" {
  type = string
}
variable "api_client_id" {
  type    = string
  default = ""
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
variable "container_app_environment_id" {
  type = string
  validation {
    condition     = !var.enabled || var.container_app_environment_id == "/subscriptions/${var.subscription_id}/resourceGroups/${var.resource_group_name}/providers/Microsoft.App/managedEnvironments/cae-newsloom-${var.environment_name}"
    error_message = "Reuse only the existing owning Container Apps environment."
  }
}
variable "registry_endpoint" {
  type = string
  validation {
    condition     = !var.enabled || var.registry_endpoint == "acrnewsloom${replace(var.environment_name, "-", "")}${substr(sha256("${var.subscription_id}/${var.environment_name}"), 0, 8)}.azurecr.io"
    error_message = "Use only the existing owning registry endpoint."
  }
}
variable "identity_base64" {
  type    = string
  default = ""
  validation {
    condition = !var.enabled || try(
      jsondecode(base64decode(var.identity_base64)).id == "/subscriptions/${var.subscription_id}/resourceGroups/${var.resource_group_name}/providers/Microsoft.ManagedIdentity/userAssignedIdentities/id-newsloom-${var.environment_name}-agent" &&
      can(regex("^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$", jsondecode(base64decode(var.identity_base64)).client_id)) &&
      can(regex("^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$", jsondecode(base64decode(var.identity_base64)).principal_id)),
      false
    )
    error_message = "Use the separate agent identity layer's exact owned identity output."
  }
}
variable "image" {
  type    = string
  default = ""
  validation {
    condition     = !var.enabled || can(regex("^${replace(var.registry_endpoint, ".", "\\.")}/newsloom-agent@sha256:[a-f0-9]{64}$", var.image))
    error_message = "Use the immutable owning agent image from the retained registry."
  }
}
variable "image_revision" {
  type    = string
  default = ""
  validation {
    condition     = !var.enabled || can(regex("^[a-f0-9]{64}$", var.image_revision))
    error_message = "Use the verified agent image input revision."
  }
}
variable "mcp_api_client_id" {
  type = string
}
variable "mcp_resource_url" {
  type = string
  validation {
    condition     = !var.enabled || can(regex("^https://[a-z0-9]+([.-][a-z0-9]+)*/mcp$", var.mcp_resource_url))
    error_message = "Use the existing fixed HTTPS MCP resource, without credentials, query or fragment."
  }
}
variable "allowed_origins" {
  type    = set(string)
  default = []
  validation {
    condition     = alltrue([for value in var.allowed_origins : can(regex("^https://[a-z0-9]+([.-][a-z0-9]+)*(:[0-9]+)?$", value))])
    error_message = "Browser origins must be explicit canonical HTTPS origins; default is none."
  }
}
variable "model_endpoint" {
  type    = string
  default = ""
  validation {
    condition     = !var.enabled || can(regex("^https://[a-z0-9-]+\\.services\\.ai\\.azure\\.com/?$", var.model_endpoint))
    error_message = "Use the retained Foundry model endpoint, without a path, query or credential."
  }
}
variable "chat_deployment" {
  type    = string
  default = ""
  validation {
    condition     = !var.enabled || can(regex("^[A-Za-z0-9_-]{1,128}$", var.chat_deployment))
    error_message = "Use the existing owning chat-completions deployment."
  }
}
variable "applicationinsights_connection_string" {
  type      = string
  default   = ""
  sensitive = true
  validation {
    condition     = !var.enabled || length(trimspace(var.applicationinsights_connection_string)) > 0
    error_message = "Authenticated telemetry requires the retained Application Insights routing configuration."
  }
}
variable "tags" {
  type    = map(string)
  default = {}
}
