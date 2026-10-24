variable "subscription_id" {
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
    condition     = can(regex("^[a-z0-9]+\\.azurecr\\.io/newsloom-enrichment@sha256:[a-f0-9]{64}$", var.image))
    error_message = "Supply the immutable enrichment image from the existing build helper."
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
variable "generation_deployment" {
  type = string
}
variable "generation_model" {
  type = string
}
variable "generation_version" {
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
variable "schedule_enabled" {
  type    = bool
  default = false
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
