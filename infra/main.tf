locals {
  tags = merge(var.tags, {
    azd-env-name = var.environment_name
  })
}

# Application resources belong to the platform-skeleton change, not bootstrap.
