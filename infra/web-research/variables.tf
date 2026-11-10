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
variable "tags" {
  type    = map(string)
  default = {}
}
