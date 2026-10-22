output "RS_RESOURCE_GROUP" {
  description = "Resource group consumed by the application layer's RBAC backend."
  value       = azurerm_resource_group.state.name
}

output "RS_STORAGE_ACCOUNT" {
  description = "Storage account consumed by the application layer's RBAC backend."
  value       = azurerm_storage_account.state.name
}

output "RS_CONTAINER_NAME" {
  description = "Private container consumed by the application layer's RBAC backend."
  value       = azurerm_storage_container.state.name
}
