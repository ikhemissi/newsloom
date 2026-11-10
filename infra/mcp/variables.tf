variable "snapshot_url" {
  type    = string
  default = ""
  validation {
    condition     = var.snapshot_url == "" || can(regex("^https://[a-z0-9]+\\.blob\\.core\\.windows\\.net/snapshots/latest\\.json\\.gz$", var.snapshot_url))
    error_message = "The read snapshot must be the private snapshots blob."
  }
}
variable "news_api_enabled" {
  type    = bool
  default = false
}
variable "allowed_origins_base64" {
  type    = string
  default = ""
  validation {
    condition = var.allowed_origins_base64 == "" || try(
      can(tolist(jsondecode(base64decode(var.allowed_origins_base64)))) &&
      alltrue([for value in jsondecode(base64decode(var.allowed_origins_base64)) :
        can(regex("^https://[a-z0-9]+([.-][a-z0-9]+)*(:[0-9]+)?$", value))
      ]), false
    )
    error_message = "Use the prepared canonical HTTPS origin array."
  }
}
variable "subscription_id" {
  type = string
}
variable "tenant_id" {
  type = string
}
variable "api_client_id" {
  type = string
}
variable "environment_name" {
  type = string
}
variable "resource_group_name" {
  type = string
}
variable "location" {
  type = string
}
variable "container_app_environment_id" {
  type = string
}
variable "registry_endpoint" {
  type = string
}
variable "workload_identities_base64" {
  type = string
}
variable "image" {
  type = string
  validation {
    condition     = can(regex("^[a-z0-9]+\\.azurecr\\.io/newsloom-mcp@sha256:[a-f0-9]{64}$", var.image))
    error_message = "Supply the immutable MCP image from the existing registry build helper."
  }
}
variable "postgres_host" {
  type = string
}
variable "postgres_database" {
  type = string
}
variable "model_endpoint" {
  type = string
}
variable "embedding_deployment" {
  type = string
}
variable "embedding_model" {
  type = string
}
variable "embedding_version" {
  type = string
}
variable "allowed_origins" {
  type    = set(string)
  default = ["https://vscode.dev"]
  validation {
    condition     = alltrue([for origin in var.allowed_origins : startswith(origin, "https://") && !strcontains(origin, "*")])
    error_message = "Origins must be explicit HTTPS values, not wildcards."
  }
}
variable "applicationinsights_connection_string" {
  type      = string
  sensitive = true
}
variable "tags" {
  type     = map(string)
  default  = {}
  nullable = false
}
variable "feedback_reviewer_object_ids" {
  description = "Comma-separated Entra object IDs allowed to review feedback; set via azd env, never committed."
  type        = string
  default     = ""
  nullable    = false
  validation {
    condition = var.feedback_reviewer_object_ids == "" || alltrue([
      for value in split(",", var.feedback_reviewer_object_ids) :
      can(regex("^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", value))
    ])
    error_message = "Use comma-separated lowercase Entra object IDs without spaces."
  }
}
variable "news_briefing_enabled" {
  type    = bool
  default = false
  validation {
    condition     = !var.news_briefing_enabled || var.news_api_enabled
    error_message = "Briefing reads require the existing protected news API."
  }
}
