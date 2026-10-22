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
  description = "Optional caller-supplied common tags."
  type        = map(string)
  default     = {}
  nullable    = false
}

variable "resource_group_name" {
  description = "Application group, separate from the existing state group."
  type        = string
}

variable "postgres_sku" {
  description = "Explicit, capacity-checked PostgreSQL SKU; no automatic fallback."
  type        = string
}

variable "postgres_storage_mb" {
  description = "Reviewed PostgreSQL storage allocation in MiB."
  type        = number
}

variable "postgres_backup_days" {
  description = "Reviewed PostgreSQL backup retention."
  type        = number
}

variable "log_retention_days" {
  description = "Workspace and Application Insights retention."
  type        = number
}

variable "log_daily_cap_gb" {
  description = "Development telemetry cap; ingestion can exceed the cap before enforcement."
  type        = number
}

variable "models" {
  description = "Explicit model contracts, verified against the regional catalog and quota."
  type = map(object({
    deployment_name = string
    name            = string
    version         = string
    format          = string
    sku             = string
    capacity        = number
  }))

  validation {
    condition     = toset(keys(var.models)) == toset(["enrichment", "embeddings", "screening"])
    error_message = "Configure exactly the enrichment, embeddings, and screening deployments."
  }

  validation {
    condition = alltrue([
      for model in values(var.models) : (
        alltrue([for value in [model.deployment_name, model.name, model.version] : length(trimspace(value)) > 0]) &&
        contains(["OpenAI", "Microsoft"], model.format) &&
        contains(["Standard", "DataZoneStandard"], model.sku) &&
        model.capacity >= 1 && model.capacity == floor(model.capacity)
      )
    ])
    error_message = "Models require explicit names/versions, a supported metered SKU/format, and positive integer capacity."
  }

  validation {
    condition     = length(distinct([for model in values(var.models) : model.deployment_name])) == 3
    error_message = "Model deployment names must be distinct."
  }
}
