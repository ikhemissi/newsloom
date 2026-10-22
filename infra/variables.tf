variable "subscription_id" {
  description = "Selected subscription, supplied by the ignored azd environment."
  type        = string
}

variable "environment_name" {
  description = "Existing developer environment name; keep stable across slices."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{0,31}$", var.environment_name))
    error_message = "Use a lowercase environment name starting with a letter, up to 32 characters."
  }
}

variable "location" {
  description = "Core Azure region, selected during platform-skeleton capacity checks."
  type        = string
}

variable "tags" {
  description = "Common tags inherited by all resources added in subsequent slices."
  type        = map(string)
  default     = {}
}
