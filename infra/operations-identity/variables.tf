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
variable "workload_identities_base64" {
  type = string
}
variable "postgres_server_name" {
  type = string
}
variable "backup_immutable_days" {
  type    = number
  default = 30
}
variable "backup_retention_days" {
  type    = number
  default = 60
  validation {
    condition     = var.backup_retention_days > var.backup_immutable_days
    error_message = "Exports must outlive their immutability period."
  }
}
variable "tags" {
  type    = map(string)
  default = {}
}
