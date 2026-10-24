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
