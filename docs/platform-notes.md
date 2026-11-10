# Platform planning notes

These notes retain infrastructure and operational details that complement
[PRD-1](prd-1.md), its [capabilities and user stories](prd-1-capabilities.md),
and [the ADRs](adrs.md). They are not a second product specification.

## Delivered platform foundation

The `platform-skeleton` slice (Step 1.1) is
[verified and archived](../openspec/changes/archive/2026-10-23-platform-skeleton/tasks.md#acceptance-evidence).
Its delivered resource contract is the
[persistent-platform main spec](../openspec/specs/persistent-azure-platform/spec.md);
deployment and preservation procedures live in the [platform runbook](azure-platform.md).
Future runtime requirements remain in
[P1-C09](prd-1-capabilities.md#p1-c09-independently-deployable-persistent-azure-platform).

## MCP client interoperability

The installed client's registration-prompt examples were not sufficient proof of
its actual callback: browser sign-in used localhost with an ephemeral port.
Entra resource indicators also required the exact MCP URL as an alias of the
existing v2 API, and Copilot needed its private flat OAuth client configuration
instead of relying on legacy VS Code forwarding. These were measured integration
issues, not reasons to add a proxy, secret, broader grant or token bypass.
The [MCP runbook](mcp.md) owns the current setup and troubleshooting procedure;
the [acceptance record](../openspec/changes/archive/2026-10-26-mcp-server/tasks.md#acceptance-evidence)
retains the actual corrections and client/tool results.

## PostgreSQL capacity and server stability

PostgreSQL B1ms capacity can be unavailable in a chosen region. Check regional
availability and select the region and SKU during `platform-skeleton`, before
provisioning. B1ms is a capacity caveat, not a mandated SKU.

Avoid replacing the PostgreSQL server after that choice. Evolve the existing
developer environment incrementally rather than casually recreating its datastore.

## Real-world feed sizes

Feeds can contain full article text and reach 4 MB. Retain a representative
large, full-text feed fixture instead of assuming feeds contain only short summaries.
The 4 MB example is an observed input size, not a required maximum or an instruction
to disable retrieval limits.

Relative links, conditional-request validators, forced refetches, and hostile
documents are covered by
[P1-C02](prd-1-capabilities.md#p1-c02-safe-feed-retrieval-and-normalization).

## Governance tags on Terraform state storage (2026-11-09)

Every resource, including the bootstrap state resource group and storage account,
must keep the `CostControl` and `SecurityControl` tags from `RESOURCE_TAGS`. When
they were missing on the state storage, tenant governance disabled its public
network access, and every layer's `terraform init` failed with a storage
`AuthorizationFailure` (403). Recover with `azd provision bootstrap --preview`
(it should only restore the tags and `public_network_access`), then apply after
review. The bootstrap layer keeps local state, so it is not blocked by the outage.

## Governance automation (2026-11-10)

Overnight on 2026-11-09 the tenant's governance automation stopped the
PostgreSQL server (23:06 UTC) and removed the `CostControl` and
`SecurityControl` tags from most resources in several passes until 02:35 UTC.
With the database stopped, the MCP readiness probe returned 503 and the site was
down until an operator started the server and merged the tags back. Nothing was
deleted and network settings were unchanged. The response is the
[operations runbook](operations.md): daily exports outside the server, delete
locks, 35-day point-in-time retention, a nightly stop and a morning wake that
repairs the tags. A deployment that runs while tags are missing re-adds them
(the preview shows only tag additions).
