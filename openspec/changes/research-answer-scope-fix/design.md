# Design

## Context

See the [proposal](proposal.md) and [delta](specs/news-research/spec.md).
The existing planning schema takes a typed `PlanningScope`. Final synthesis
uses generic `ResearchAnswer` JSON schema, although the controller already
knows coverage and missing IDs and the renderer validates them.
The live b05 diagnostic returned the server's safe `research_coverage_invalid`
category; the failed baseline and all reservations remain preserved.

## Goals / Non-Goals

**Goals:** use the existing trusted-scope pattern for deterministic final
metadata and preserve independent validation and all request limits.

**Non-Goals:** changing substantive claims, citation rules, filters, tool/model
budgets, models, permissions, evaluation criteria or repairing returned output.

## Decisions

- Add a typed synthesis scope containing coverage and missing IDs, supplied
  explicitly by the controller rather than parsed from untrusted context.
- Specialize the final JSON schema to the scope's single coverage value and
  missing-ID membership/count. Avoid an empty enum for an empty missing set.
  Keep the existing distinct-ID and renderer checks authoritative.
- Update the typed model interface and all direct/scripted callers together.
  A provider ignoring the schema must still fail; no silent override/default.
- Reject the alternatives of prompt-only reminders, parsing controls from
  the content context, overriding returned metadata or adding repair calls.
  They either retain the observed failure mode or bypass the delivered contract.

## Risks / Trade-offs

- SDK/schema compatibility -> actual pinned-provider wire tests for selected,
  discovery, empty and missing-item scopes.
- Mistaking structural checks for semantic quality -> verify only the stated
  coverage invariant; leave the full baseline and report gates open.
- Deployment changes accepted runtime provenance -> retain the prior image
  and failed run, publish a separate new image/configuration receipt and bind
  any later baseline to it without relabelling historical evidence.

## Migration Plan

Run focused tests/types/lint, primary checks and package builds. Use only the
existing agent build and agent-layer preview. Admit only the immutable image/
revision update with unchanged identity/configuration and no resource change,
then apply through azd and independently verify the deployed agent. Run one
bounded same-user discovery case, preserving costs and privacy. Publish
implementation and measured evidence with exact-source CI before completion.
Rollback uses the prior accepted immutable image/revision with an owning
reviewed agent-only preview; do not recreate infrastructure or broaden access.
