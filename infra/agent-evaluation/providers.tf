terraform {
  required_version = ">= 1.15.8, < 2.0.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "= 5.10.0"
    }
    azapi = {
      source  = "azure/azapi"
      version = "= 2.13.0"
    }
  }

  backend "azurerm" {
    use_azuread_auth = true
  }
}

provider "azapi" {
  subscription_id            = var.subscription_id
  tenant_id                  = var.tenant_id
  use_cli                    = true
  use_msi                    = false
  use_oidc                   = false
  skip_provider_registration = true
  disable_default_output     = true
}

provider "azurerm" {
  features {}
  subscription_id                 = var.subscription_id
  resource_provider_registrations = "none"
  storage_use_azuread             = true
}
