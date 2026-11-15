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
variable "github_subjects" {
  type = set(string)
  default = [
    "repo:ikhemissi@1769608/newsloom@1429962749:pull_request",
    "repo:ikhemissi@1769608/newsloom@1429962749:ref:refs/heads/main",
  ]
  validation {
    condition = var.github_subjects == toset([
      "repo:ikhemissi@1769608/newsloom@1429962749:pull_request",
      "repo:ikhemissi@1769608/newsloom@1429962749:ref:refs/heads/main",
    ])
    error_message = "Federation requires the approved immutable owner/repository IDs: pull requests and the exact main ref."
  }
}
variable "tags" {
  type    = map(string)
  default = {}
}
