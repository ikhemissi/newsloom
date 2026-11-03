variable "enabled" {
  type    = bool
  default = false
}
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
variable "registry_id" {
  type = string
}
variable "applicationinsights_id" {
  type = string
}
variable "model_account_id" {
  type = string
}
variable "enrichment_deployment" {
  type = string
}
variable "generation_deployment" {
  type    = string
  default = ""
  validation {
    condition     = !var.enabled || (var.generation_deployment != "" && var.generation_deployment != var.enrichment_deployment)
    error_message = "Briefing requires a separate deployment, never the existing enrichment deployment."
  }
}
variable "generation_model" {
  type = string
}
variable "generation_version" {
  type = string
}
variable "generation_sku" {
  type = string
}
variable "tags" {
  type    = map(string)
  default = {}
}
