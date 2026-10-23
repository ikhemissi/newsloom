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
    condition     = can(regex("^[a-z0-9]+\\.azurecr\\.io/newsloom-ingestion@sha256:[a-f0-9]{64}$", var.image))
    error_message = "Supply the immutable ingestion image produced by the azd build hook."
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
variable "screening_deployment" {
  type = string
}
variable "screening_threshold" {
  type    = string
  default = ""
  validation {
    condition     = var.screening_threshold == "" || try(tonumber(var.screening_threshold) >= 0 && tonumber(var.screening_threshold) <= 1, false)
    error_message = "Only the measured finite probability threshold is valid."
  }
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
