output "resource_group_name" {
  description = "Set as RS_RESOURCE_GROUP in the ignored azd environment."
  value       = azurerm_resource_group.state.name
}

output "storage_account_name" {
  description = "Set as RS_STORAGE_ACCOUNT in the ignored azd environment."
  value       = azurerm_storage_account.state.name
}

output "container_name" {
  description = "Set as RS_CONTAINER_NAME in the ignored azd environment."
  value       = azurerm_storage_container.state.name
}
