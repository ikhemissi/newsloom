variable "subscription_id" {
  type = string
}

variable "environment_name" {
  type = string
}

variable "location" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "container_app_environment_id" {
  type = string
}

variable "registry_endpoint" {
  type = string
}

variable "image" {
  type        = string
  description = "Real image built in ACR, referenced by its immutable digest."

  validation {
    condition     = can(regex("^[a-z0-9]+\\.azurecr\\.io/newsloom-platform@sha256:[a-f0-9]{64}$", var.image))
    error_message = "Supply the immutable Newsloom image produced by the azd build hook."
  }
}

variable "workload_identities_base64" {
  type        = string
  description = "Base64-encoded JSON avoids nested-quote corruption in azd's JSON input template."
}

variable "postgres_host" {
  type = string
}

variable "postgres_database" {
  type = string
}

variable "postgres_admin_name" {
  type = string
}

variable "model_endpoint" {
  type = string
}

variable "model_account_id" {
  type = string
}

variable "enrichment_deployment" {
  type = string
}

variable "embeddings_deployment" {
  type = string
}

variable "screening_deployment" {
  type = string
}

variable "applicationinsights_connection_string" {
  type      = string
  sensitive = true
}

variable "verification_enabled" {
  type        = bool
  default     = false
  description = "Create only the explicitly named temporary managed-identity verification jobs."
}

variable "tags" {
  description = "Optional caller-supplied common tags."
  type        = map(string)
  default     = {}
  nullable    = false
}
