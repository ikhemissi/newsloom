# Proposal

## Why

[Phase 1 is accepted](../../../docs/phase1-acceptance.md#verified-phase-acceptance-matrix)
and its delivered contracts are archived. The next slice,
[PRD-2 Step 2.1](../../../docs/prd-2.md#delivery-plan), must establish a real
authenticated agent boundary without assuming that a managed identity can act
on behalf of a user.

## What Changes

- Deliver [P2-C01 and P2-C02](../../../docs/prd-2-capabilities.md): a Python
  Microsoft Agent Framework A2A service on the existing ACA environment, with
  agent-card discovery, authenticated requests and streamed responses.
- Make live secretless OBO the first go/no-go gate: an actual signed-in A2A
  client must reach one existing read-only MCP tool through the agent while
  preserving the user's identity. A configured credential, local mock or
  application-only token does not satisfy that gate.
- Give the agent its own user-assigned identity, middle-tier API registration
  and exact managed-identity federated credential. Use a separate public PKCE
  acceptance client, leaving the working MCP public client unchanged. The
  middle tier receives only delegated `news.read`, never standing MCP
  application access or a database role.
- After OBO passes, connect one bounded recent-news demonstrator to the existing
  Foundry chat deployment and stream its response over A2A. This is a transport
  and identity slice, not a completed research experience.
- Add owning identity/app layers, immutable packaging, explicit verification
  helpers and content-free diagnostics using the existing repository patterns.
  Preserve production resources, MCP authorization, both schedules and history.

**Prerequisites:** accepted Phase 1; archive commit `66b3fff` with
[passing exact-head CI](https://github.com/ikhemissi/newsloom/actions/runs/40331652459);
reviewed directory permissions/consent and owning azd previews before any cloud
mutation. This proposal authorizes no deployment or implementation.

**Out of scope:** multi-step research, research/citation-quality claims and frozen
phase-wide agent evaluations (Steps 2.2-2.3); browser UI or UI transport/framework
selection; multi-agent orchestration; persistent conversation storage; new model
deployments/capacity; changes to screening, enrichment, retrieval or historical
quarantine/dead letters; secret, proxy, app-only or direct-database fallbacks.

## Capabilities

### New Capabilities

- `a2a-serving`: Discoverable authenticated A2A requests, caller-isolated
  streaming and bounded independent agent delivery.
- `delegated-mcp-access`: Secretless middle-tier OBO, request-scoped delegated
  MCP access, explicit denial behavior and real user-preservation evidence.

### Modified Capabilities

None. Existing MCP audiences, delegated scope, tool contracts and workload
boundaries remain authoritative and unchanged.

## Impact

- **Proposed code:** a new `services/agent` workspace package; narrowly reusable
  token-verification/privacy helpers; typed OBO and MCP adapters; focused HTTP,
  identity, cancellation and privacy tests. Do not import the MCP server as the
  agent's client or duplicate its authentication implementation.
- **Proposed infrastructure:** owning `agent-identity` and `agent` azd/Terraform
  layers in retained state. One new small ACA app and its own identity,
  registrations, exact federation, registry-pull/telemetry and chat-only inference
  grants; no new database, Foundry project, model or verification job.
- **Dependencies:** resolve and pin compatible Agent Framework/A2A server and
  client packages on Python 3.15, retaining isolated-package startup checks.
  Official documentation supports A2A server adapters and the async Azure
  Identity OBO credential's synchronous assertion callback; actual dependency
  compatibility and live exchange are still unverified here.
- **Blocking identity question:** prove the same-tenant managed-identity
  assertion, intended agent audience and preconsented downstream `news.read`
  exchange in Azure. If unsupported or denied, stop; do not add a client secret,
  another access path or a broader grant.
- **Capacity, model and cost:** prefer the existing region and pinned
  `gpt-5.4-mini` chat-completions deployment. Confirm framework compatibility,
  shared quota and a metered replica/token estimate before apply. New capacity,
  model, region or broader inference authority requires a separate decision.
- **Status:** planning only. No agent package, dependency, registration,
  identity, cloud resource or model call has been created by this proposal.
