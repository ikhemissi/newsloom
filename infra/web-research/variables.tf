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
variable "model_account_id" {
  type = string
}
variable "agent_identity_base64" {
  type    = string
  default = ""
  validation {
    condition     = !var.enabled || var.agent_identity_base64 != ""
    error_message = "Web research needs the agent identity."
  }
}
variable "foundry_user_role_id" {
  type    = string
  default = ""
  validation {
    condition     = var.foundry_user_role_id == "" || sha256(var.foundry_user_role_id) == "1b2c85d975c797931286727893ff9d47615ac3276658f4aeb3c20ffcd44422dd"
    error_message = "Use only the publicly documented Foundry User role ID."
  }
}
variable "tags" {
  type    = map(string)
  default = {}
}
