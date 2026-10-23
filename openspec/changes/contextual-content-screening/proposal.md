# Proposal

## Why

The current Decision question conflates the presence of AI-directed instructions
with an attempt to hijack Newsloom. Reviewing the 23 quarantined article identities
found legitimate tutorial prompts, quoted security examples, and publisher
training-use notices; production also scores a different input shape from the
current short-string calibration fixtures.

## What Changes

- Deliver one PRD-1 P1-C03 follow-up, after the verified
  [ingestion](../feed-ingestion/tasks.md) and
  [resilience](../resilient-feed-ingestion/tasks.md) changes, before enrichment.
- Ask whether untrusted source content attempts to redirect its consuming
  processor, rather than treating any AI instructions as malicious. Contextual
  reporting is not an automatic exemption for an operative attack.
- Calibrate and validate using complete normalized entries, including metadata,
  with benign security reporting and disguised attacks represented separately.
- Add a bounded local comparison of the current and candidate policy using the
  existing Decision deployment and signed-in developer credentials. Evaluation
  must not implicitly start Azure jobs, write database rows, or change deployment
  settings. After local authorization failed, the user explicitly requested
  verification in the existing ingestion job using its current managed identity.
  Support that explicit execution mode without another grant or worker.
- Use the 23 reviewed identities as private, explicitly labelled regressions,
  not unseen validation. Distinguish current feed reconstructions from historical
  database inputs and record missing matches and truncation.
- **BREAKING (configuration):** bind the deployed threshold to the evaluated
  rubric, packaged fixture revision, and model configuration. The updated runtime
  must fail closed on missing or mismatched calibration metadata instead of
  silently reusing the old policy's threshold.
- Preserve numeric admission, deferred operational failures, rate limits,
  telemetry privacy, and every existing rejected quarantine row. Deploy only
  after offline checks and measured comparison acceptance, then verify ordinary
  ingestion immediately in Azure. The comparison may run as an explicit
  execution of the existing job before activating the candidate for admission.

Out of scope: enrichment prompts or runtime, MCP serving, Prompt Shields,
Spotlighting, another model or gate, publisher whitelists, automatic quarantine
release, database migrations, new dependencies, and new cloud resources.

## Capabilities

### New Capabilities

None; evaluation and contextual admission belong to the existing scanner boundary.

### Modified Capabilities

- `content-screening`: contextual injection criteria, production-shaped
  calibration, policy-bound thresholds, and private side-effect-free local
  comparison before deployment.

## Impact

- Extend the existing [scanner](../../../services/ingestion/src/newsloom_ingestion/scanner.py),
  packaged calibration fixtures, ingestion CLI, and focused scanner/CLI tests.
  Reuse protected feed parsing/recovery only for the explicitly selected review
  inputs; ordinary local feed smoke-test restrictions remain unchanged.
- Wire the compact calibration binding through the existing ingestion azd/Terraform
  configuration and tests. No queue/quarantine schema or privilege changes.
- Update the [ingestion runbook](../../../docs/ingestion.md),
  [phase capabilities](../../../docs/prd-1-capabilities.md),
  [ADR-6](../../../docs/adrs.md), and phase status in their owning documents.
- Reuse the current model, region, capacity, identities, schedule, and persistent
  azd environment. Local inference is metered and shares deployment quota.
  Signed-in developer inference authorization needs a preflight; missing access,
  model unavailability, inseparable scores, or failed validation blocks rollout,
  not permission to add keys, grants, resources, or a fallback automatically.
