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

variable "foundry_user_role_id" {
  type    = string
  default = ""
  validation {
    condition     = var.foundry_user_role_id == "" || sha256(var.foundry_user_role_id) == "1b2c85d975c797931286727893ff9d47615ac3276658f4aeb3c20ffcd44422dd"
    error_message = "Use only the publicly documented Foundry User role ID, or empty to retain the original foundation."
  }
}

variable "foundry_project_manager_role_id" {
  type    = string
  default = ""
  validation {
    condition     = var.foundry_project_manager_role_id == "" || sha256(var.foundry_project_manager_role_id) == "3513cfcf768dd13c016590ae6bc57b6870e9f0d04bce2ee2458f13473ee64610"
    error_message = "Use only the publicly documented Foundry Project Manager role ID, or empty to retain existing authority."
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

variable "data_resources" {
  type = object({
    enabled                                = optional(bool, false)
    import_existing                        = optional(bool, false)
    storage_name                           = optional(string, "")
    connection_name                        = optional(string, "")
    storage_grant_name                     = optional(string, "")
    account_user_grant_name                = optional(string, "")
    account_manager_grant_name             = optional(string, "")
    storage_role_id                        = optional(string, "")
    appinsights_id                         = optional(string, "")
    appinsights_reader_name                = optional(string, "")
    appinsights_publisher_name             = optional(string, "")
    appinsights_reader_role_id             = optional(string, "")
    appinsights_publisher_role_id          = optional(string, "")
    retain_experimental_appinsights_grants = optional(bool, false)
  })
  default = {}

  validation {
    condition = (
      !var.data_resources.enabled ||
      (
        var.enabled &&
        var.foundry_user_role_id != "" &&
        var.foundry_project_manager_role_id != "" &&
        (var.data_resources.storage_name == "" || can(regex("^[a-z0-9]{3,24}$", var.data_resources.storage_name))) &&
        (var.data_resources.connection_name == "" || can(regex("^[a-zA-Z0-9][a-zA-Z0-9_-]{2,32}$", var.data_resources.connection_name))) &&
        sha256(var.data_resources.storage_role_id) == "fe1e07b465de108d9fbd5aa7a702768beecabda8211f3a72a19c624a97a0d0cd" &&
        alltrue([for name in [
          var.data_resources.storage_grant_name,
          var.data_resources.account_user_grant_name,
          var.data_resources.account_manager_grant_name,
        ] : var.data_resources.import_existing ? can(regex("^[a-f0-9-]{36}$", name)) : name == "" || can(regex("^[a-f0-9-]{36}$", name))])
      )
    )
    error_message = "Evaluation data resources require the retained foundation, approved roles and valid exact adoption names."
  }

  validation {
    condition = (
      !var.data_resources.retain_experimental_appinsights_grants ||
      (
        var.data_resources.enabled &&
        lower(var.data_resources.appinsights_id) == lower("/subscriptions/${var.subscription_id}/resourceGroups/${var.resource_group_name}/providers/Microsoft.Insights/components/appi-newsloom-${var.environment_name}") &&
        can(regex("^[a-f0-9-]{36}$", var.data_resources.appinsights_reader_name)) &&
        can(regex("^[a-f0-9-]{36}$", var.data_resources.appinsights_publisher_name)) &&
        sha256(var.data_resources.appinsights_reader_role_id) == "ff5a1403c3544342c98473431511f4589219ab5ba57f30e7624c3c6e6d6bf8b3" &&
        sha256(var.data_resources.appinsights_publisher_role_id) == "451512f3ee32ea6c09538a7f7cc2f3269c8d67fcf337fd1939ab9ba665e320ee"
      )
    )
    error_message = "Diagnostic telemetry grants may be adopted only at the retained Application Insights resource with the exact approved roles."
  }
}
