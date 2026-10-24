variable "tenant_id" {
  type = string
}
variable "environment_name" {
  type = string
}
variable "existing_api_object_id" {
  type    = string
  default = ""
}
variable "existing_client_object_id" {
  type    = string
  default = ""
}
variable "existing_api_principal_id" {
  type    = string
  default = ""
}
variable "existing_client_principal_id" {
  type    = string
  default = ""
}
variable "existing_api_client_id" {
  type    = string
  default = ""
}
variable "existing_scope_id" {
  type    = string
  default = ""
}
variable "resource_url" {
  type    = string
  default = ""
  validation {
    condition = (
      var.resource_url == "" ||
      can(regex("^https://[a-z0-9]+([.-][a-z0-9]+)*/mcp$", var.resource_url))
    )
    error_message = "Use only the exact canonical HTTPS MCP resource URL, without query or trailing slash."
  }
}
variable "existing_resource_identifier" {
  type    = bool
  default = false
}
variable "redirect_uris" {
  type = set(string)
  default = [
    "http://localhost",
    "http://127.0.0.1:33418",
    "https://vscode.dev/redirect",
  ]
  validation {
    condition = (
      length(var.redirect_uris) > 0 &&
      alltrue([for uri in var.redirect_uris : contains([
        "http://localhost", "http://127.0.0.1:33418", "https://vscode.dev/redirect",
      ], uri)])
    )
    error_message = "Only the observed installed VS Code callback URIs are approved."
  }
}
