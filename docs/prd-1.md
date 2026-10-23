# PRD-1: MCP news platform

Status: in progress. Prerequisite:
[bootstrap acceptance](../openspec/changes/archive/2026-10-22-bootstrap/tasks.md) is complete.
Step 1.1 is complete and
[verified](../openspec/changes/archive/2026-10-23-platform-skeleton/tasks.md#acceptance-evidence).
Steps 1.2-1.6 and phase acceptance remain pending.

This document owns phase sequencing and capability-to-slice assignments.
[Capabilities](prd-1-capabilities.md) own behavior, user stories, acceptance
criteria, and unresolved product decisions. See [the ADRs](adrs.md) for technical
choices and [platform notes](platform-notes.md) for operational lessons.

## Delivery plan

| Step | Slice | Capability scope |
| --- | --- | --- |
| 1.1 | `platform-skeleton` | [P1-C08](prd-1-capabilities.md#p1-c08-user-authentication-and-least-privilege-workload-access), [P1-C09](prd-1-capabilities.md#p1-c09-independently-deployable-persistent-azure-platform), [P1-C10](prd-1-capabilities.md#p1-c10-safe-operational-visibility) foundations |
| 1.2 | `feed-ingestion` | [P1-C01](prd-1-capabilities.md#p1-c01-configuration-driven-source-curation), [P1-C02](prd-1-capabilities.md#p1-c02-safe-feed-retrieval-and-normalization), [P1-C03](prd-1-capabilities.md#p1-c03-content-screening-and-quarantine) interface, [P1-C04](prd-1-capabilities.md#p1-c04-idempotent-ingestion-and-durable-processing) ingestion, [P1-C10](prd-1-capabilities.md#p1-c10-safe-operational-visibility) ingestion instrumentation |
| 1.3 | `content-security` | [P1-C03](prd-1-capabilities.md#p1-c03-content-screening-and-quarantine) model scanner, [P1-C10](prd-1-capabilities.md#p1-c10-safe-operational-visibility) scanner instrumentation |
| 1.4 | `enrichment` | [P1-C04](prd-1-capabilities.md#p1-c04-idempotent-ingestion-and-durable-processing) processing, [P1-C05](prd-1-capabilities.md#p1-c05-structured-model-enrichment-and-embeddings), [P1-C10](prd-1-capabilities.md#p1-c10-safe-operational-visibility) job instrumentation |
| 1.5 | `mcp-server` | [P1-C06](prd-1-capabilities.md#p1-c06-recent-news-item-details-and-source-discovery), [P1-C07](prd-1-capabilities.md#p1-c07-filtered-semantic-search), [P1-C08](prd-1-capabilities.md#p1-c08-user-authentication-and-least-privilege-workload-access) user access, [P1-C10](prd-1-capabilities.md#p1-c10-safe-operational-visibility) service instrumentation |
| 1.6 | Phase tests/evals | [P1-C11](prd-1-capabilities.md#p1-c11-evidence-based-platform-acceptance) |

Use [the development guide](development.md#openspec) to execute each slice.
