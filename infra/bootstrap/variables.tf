variable "subscription_id" {
  description = "Subscription to bootstrap; supply in an ignored local tfvars file."
  type        = string
}

variable "location" {
  description = "Azure region for the persistent state account."
  type        = string
}

variable "resource_group_name" {
  description = "Dedicated resource group for the persistent Terraform state account."
  type        = string
}

variable "storage_account_name" {
  description = "Globally unique state account name."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9]{3,24}$", var.storage_account_name))
    error_message = "Storage account names must contain 3-24 lowercase letters or digits."
  }
}

variable "container_name" {
  description = "Private container used for azd Terraform state."
  type        = string
  default     = "tfstate"

  validation {
    condition = (
      can(regex("^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$", var.container_name)) &&
      !strcontains(var.container_name, "--")
    )
    error_message = "Use a valid 3-63 character Azure container name without consecutive hyphens."
  }
}

variable "tags" {
  description = "Common tags for state infrastructure."
  type        = map(string)
  default     = {}
}
