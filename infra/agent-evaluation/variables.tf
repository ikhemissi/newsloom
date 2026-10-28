variable "enabled" {
  type    = bool
  default = false
}

variable "subscription_id" {
  type = string
}

variable "tenant_id" {
  type    = string
  default = ""
  validation {
    condition     = !var.enabled || can(regex("^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$", var.tenant_id))
    error_message = "Use the retained tenant verified against the selected CLI account."
  }
}

variable "operator_principal_id" {
  type    = string
  default = ""
  validation {
    condition     = !var.enabled || can(regex("^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$", var.operator_principal_id))
    error_message = "Use the verified signed-in human operator, not a workload identity."
  }
}

variable "environment_name" {
  type = string
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{0,31}$", var.environment_name))
    error_message = "Use the retained application environment name."
  }
}

variable "resource_group_name" {
  type = string
  validation {
    condition     = can(regex("^[A-Za-z0-9_().-]{1,90}$", var.resource_group_name))
    error_message = "Use the retained application's resource group without path components."
  }
}

variable "location" {
  type = string
}

variable "model_account_id" {
  type    = string
  default = ""
  validation {
    condition     = !var.enabled || var.model_account_id == "/subscriptions/${var.subscription_id}/resourceGroups/${var.resource_group_name}/providers/Microsoft.CognitiveServices/accounts/ai-newsloom-${var.environment_name}-${substr(sha256("${var.subscription_id}/${var.environment_name}"), 0, 8)}"
    error_message = "Reuse the exact application-owned model account; no new account or foreign grant scope."
  }
}

variable "model_endpoint" {
  type    = string
  default = ""
  validation {
    condition     = !var.enabled || var.model_endpoint == "https://ai-newsloom-${var.environment_name}-${substr(sha256("${var.subscription_id}/${var.environment_name}"), 0, 8)}.services.ai.azure.com/"
    error_message = "Use the retained account's fixed Foundry endpoint."
  }
}

variable "tags" {
  type     = map(string)
  default  = {}
  nullable = false
}
