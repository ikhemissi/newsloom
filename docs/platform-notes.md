# Platform planning notes

These notes retain infrastructure and operational details that complement
[PRD-1](prd-1.md), its [capabilities and user stories](prd-1-capabilities.md),
and [the ADRs](adrs.md). They are not a second product specification.

## Platform-skeleton resource checklist

The `platform-skeleton` slice (Step 1.1) must explicitly provision:

- The application resource group, separate from the persistent state-bootstrap group.
- A container registry for the platform's images.
- An Azure Container Apps environment for the apps and jobs.

The remaining platform requirements and deployment acceptance are defined in
[P1-C09](prd-1-capabilities.md#p1-c09-independently-deployable-persistent-azure-platform)
and the related capabilities.

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
