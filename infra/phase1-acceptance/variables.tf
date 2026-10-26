variable "enabled" {
  type    = bool
  default = false
}
variable "subscription_id" {
  type = string
}
variable "environment_name" {
  type = string
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{0,40}$", var.environment_name))
    error_message = "Use the existing environment's safe resource-name suffix."
  }
}
variable "resource_group_name" {
  type = string
}
variable "location" {
  type = string
}
variable "container_app_environment_id" {
  type = string
  validation {
    condition     = var.container_app_environment_id == "/subscriptions/${var.subscription_id}/resourceGroups/${var.resource_group_name}/providers/Microsoft.App/managedEnvironments/cae-newsloom-${var.environment_name}"
    error_message = "Use the existing owning Container Apps environment, not another log namespace."
  }
}
variable "registry_id" {
  type = string
}
variable "registry_endpoint" {
  type = string
}
variable "model_account_id" {
  type = string
}
variable "applicationinsights_id" {
  type = string
}
variable "applicationinsights_connection_string" {
  type      = string
  sensitive = true
}
variable "image" {
  type    = string
  default = ""
  validation {
    condition     = !var.enabled || can(regex("^[a-z0-9]+\\.azurecr\\.io/newsloom-phase1@sha256:[a-f0-9]{64}$", var.image))
    error_message = "Enabled acceptance requires its own immutable registry image."
  }
}
variable "image_revision" {
  type    = string
  default = ""
  validation {
    condition     = !var.enabled || can(regex("^[a-f0-9]{64}$", var.image_revision))
    error_message = "Use the verified test image's input revision."
  }
}
variable "github_subject" {
  type    = string
  default = "repo:ikhemissi@1769608/newsloom@1429962749:ref:refs/heads/main"
  validation {
    condition     = var.github_subject == "repo:ikhemissi@1769608/newsloom@1429962749:ref:refs/heads/main"
    error_message = "Federation requires the approved immutable owner/repository IDs and exact main ref."
  }
}
variable "test_settings" {
  type = object({
    postgres_host          = string
    model_endpoint         = string
    generation_deployment  = string
    generation_model       = string
    generation_version     = string
    embedding_deployment   = string
    embedding_model        = string
    embedding_version      = string
    screening_deployment   = string
    screening_model        = string
    screening_version      = string
    scanner_threshold      = number
    scanner_calibration_id = string
  })
}
variable "tags" {
  type    = map(string)
  default = {}
}
