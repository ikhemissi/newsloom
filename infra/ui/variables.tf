variable "enabled" {
  type    = bool
  default = false
}
variable "news_enabled" {
  type    = bool
  default = false
  validation {
    condition     = !var.news_enabled || var.enabled
    error_message = "News configuration requires the existing enabled UI app."
  }
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
    error_message = "Reuse the retained ACA environment."
  }
}
variable "registry_id" {
  type = string
  validation {
    condition     = !var.enabled || var.registry_id == "/subscriptions/${var.subscription_id}/resourceGroups/${var.resource_group_name}/providers/Microsoft.ContainerRegistry/registries/acrnewsloom${replace(var.environment_name, "-", "")}${substr(sha256("${var.subscription_id}/${var.environment_name}"), 0, 8)}"
    error_message = "Registry pull must be scoped only to the retained registry."
  }
}
variable "registry_endpoint" {
  type = string
  validation {
    condition     = !var.enabled || var.registry_endpoint == "${basename(var.registry_id)}.azurecr.io"
    error_message = "Registry endpoint must match the retained registry ID."
  }
}
variable "image" {
  type    = string
  default = ""
  validation {
    condition     = !var.enabled || can(regex("^${replace(var.registry_endpoint, ".", "\\.")}/newsloom-web@sha256:[a-f0-9]{64}$", var.image))
    error_message = "Use the immutable owning UI image."
  }
}
variable "image_revision" {
  type    = string
  default = ""
  validation {
    condition     = !var.enabled || can(regex("^[a-f0-9]{64}$", var.image_revision))
    error_message = "Use the verified UI image source hash."
  }
}
variable "config_base64" {
  type    = string
  default = ""
  validation {
    condition = !var.enabled || try(
      length(keys(jsondecode(base64decode(var.config_base64)))) == (var.news_enabled ? 6 : 4) &&
      can(regex("^https://[a-z0-9]+([.-][a-z0-9]+)*/a2a$", jsondecode(base64decode(var.config_base64)).agentUrl)) &&
      can(regex("^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$", jsondecode(base64decode(var.config_base64)).tenantId)) &&
      can(regex("^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$", jsondecode(base64decode(var.config_base64)).clientId)) &&
      can(regex("^api://[a-f0-9-]+/news.agent$", jsondecode(base64decode(var.config_base64)).agentScope)) &&
      (!var.news_enabled || (var.http_api_enabled ? (
        can(regex("^https://[a-z0-9]+([.-][a-z0-9]+)*/api/v1$", jsondecode(base64decode(var.config_base64)).newsApiUrl)) &&
        can(regex("^api://[a-f0-9-]+/news.read$", jsondecode(base64decode(var.config_base64)).newsScope))
        ) : (
        can(regex("^https://[a-z0-9]+([.-][a-z0-9]+)*/mcp$", jsondecode(base64decode(var.config_base64)).mcpUrl)) &&
        can(regex("^api://[a-f0-9-]+/news.read$", jsondecode(base64decode(var.config_base64)).mcpScope))
      ))),
      false
    )
    error_message = "Use the prepared public audience-separated UI configuration, never credentials."
  }
}
variable "tags" {
  type    = map(string)
  default = {}
}
variable "http_api_enabled" {
  type    = bool
  default = false
  validation {
    condition     = !var.http_api_enabled || (var.enabled && var.news_enabled)
    error_message = "HTTP UI requires enabled news; retain the existing news consent."
  }
}
