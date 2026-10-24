terraform {
  required_version = ">= 1.15.8, < 2.0.0"
  required_providers {
    azuread = {
      source  = "hashicorp/azuread"
      version = "= 3.10.0"
    }
  }
  backend "azurerm" {
    use_azuread_auth = true
  }
}

provider "azuread" {
  tenant_id = var.tenant_id
  use_cli   = true
}
