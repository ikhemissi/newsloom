mock_provider "azapi" {}
mock_provider "azurerm" {}

variables {
  subscription_id     = join("-", ["00000000", "0000", "0000", "0000", "000000000000"])
  environment_name    = "test"
  resource_group_name = "rg-newsloom-test"
  tags                = { CostControl = "Ignore", SecurityControl = "Ignore" }
}

run "disabled_by_default" {
  command = plan
  assert {
    condition     = length(azapi_resource.webiq) == 0 && output.WEBIQ_ACCOUNT_NAME == ""
    error_message = "Web research creates nothing unless enabled."
  }
}

run "one_keyless_web_iq_account" {
  command = plan
  variables {
    enabled = true
  }
  assert {
    condition = (
      azapi_resource.webiq[0].type == "Microsoft.WebIQ/accounts@2026-06-01-preview" &&
      azapi_resource.webiq[0].name == "webiq-newsloom-test" &&
      azapi_resource.webiq[0].location == "global" &&
      azapi_resource.webiq[0].body.kind == "WebIQ.Grounding" &&
      azapi_resource.webiq[0].body.sku.name == "G3" &&
      azapi_resource.webiq[0].tags.CostControl == "Ignore" &&
      azapi_resource.webiq[0].parent_id == "/subscriptions/${var.subscription_id}/resourceGroups/rg-newsloom-test"
    )
    error_message = "One tagged Web IQ account in the application resource group."
  }
}
