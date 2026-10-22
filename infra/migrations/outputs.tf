output "MIGRATION_JOB_ID" {
  value = azurerm_container_app_job.operation["migrate"].id
}

output "PLATFORM_VERIFICATION_JOBS" {
  description = "Explicit cleanup allowlist; never includes the migration job or shared resources."
  value = jsonencode({
    for name, job in azurerm_container_app_job.operation : local.jobs[name].workload => job.id
    if startswith(name, "verify_")
  })
}
