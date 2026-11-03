variable "enabled" {
  type    = bool
  default = false
}
variable "schedule_enabled" {
  type    = bool
  default = false
  validation {
    condition     = !var.schedule_enabled || var.enabled
    error_message = "Scheduling requires the explicitly enabled briefing workload."
  }
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
variable "container_app_environment_id" {
  type = string
}
variable "registry_endpoint" {
  type = string
}
variable "identity_base64" {
  type    = string
  default = ""
  validation {
    condition     = !var.enabled || can(jsondecode(base64decode(var.identity_base64)).principal_id)
    error_message = "Prepare the additive briefing identity before the job."
  }
}
variable "image" {
  type    = string
  default = ""
  validation {
    condition     = !var.enabled || can(regex("^[a-z0-9]+\\.azurecr\\.io/newsloom-briefing@sha256:[a-f0-9]{64}$", var.image))
    error_message = "Supply the immutable briefing image from the existing build helper."
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
variable "input_price_per_million" {
  type    = string
  default = ""
  validation {
    condition     = !var.enabled || try(tonumber(var.input_price_per_million) >= 0, false)
    error_message = "Supply verified input pricing; do not silently estimate unknown usage as zero."
  }
}
variable "output_price_per_million" {
  type    = string
  default = ""
  validation {
    condition     = !var.enabled || try(tonumber(var.output_price_per_million) >= 0, false)
    error_message = "Supply verified output pricing."
  }
}
variable "price_basis" {
  type    = string
  default = ""
  validation {
    condition     = !var.enabled || can(regex("[0-9]{4}-[0-9]{2}-[0-9]{2}", var.price_basis))
    error_message = "Supply a dated, verified model price basis."
  }
}
variable "applicationinsights_connection_string" {
  type      = string
  sensitive = true
}
variable "tags" {
  type    = map(string)
  default = {}
}
