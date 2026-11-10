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
  type = string
}
variable "image" {
  type = string
  validation {
    condition     = can(regex("/newsloom-operations@sha256:[a-f0-9]{64}$", var.image))
    error_message = "Operations jobs require an immutable image digest."
  }
}
variable "postgres_host" {
  type = string
}
variable "postgres_database" {
  type = string
}
variable "postgres_server_name" {
  type = string
}
variable "backup_account_url" {
  type = string
}
variable "backup_container" {
  type = string
}
variable "schedule_enabled" {
  type    = bool
  default = true
}
variable "tags" {
  type    = map(string)
  default = {}
}
variable "state_storage_id" {
  type    = string
  default = ""
}
