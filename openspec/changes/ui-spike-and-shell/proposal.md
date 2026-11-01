# Proposal

## Why

Newsloom has a verified deployed research backend but no usable browser interface.
The user approved a narrow early-access UI before completion of PRD-2's remaining
evaluations, without treating that exception as phase acceptance.

## What Changes

- Deliver PRD-3 slice 3.1 as a complete, minimal journey: stable Entra browser
  sign-in, a research question, visible progress, a validated final answer and
  clickable citations. An empty shell or developer-only console is insufficient.
- Use React 19, Vite, strict TypeScript, Tailwind 4, daisyUI 5, MSAL, Zod and
  the official A2A JavaScript SDK. Prefer native browser APIs; no router/query
  library, CopilotKit runtime or AG-UI translation service.
- Add exact-origin agent CORS support without changing delegated authorization,
  research generation, request budgets or the existing text-only A2A contract.
- Host static assets on ACA in the retained environment/region through owning
  Terraform/azd layers. The user selected this instead of the handoff's SWA
  deployment-token exception.
- Add a separate single-tenant SPA registration with only delegated `news.agent`.
  Preserve the existing agent-to-MCP OBO path; direct browser MCP access is not
  required for this first journey.
- During implementation, update PRD-2/PRD-3 sequencing, relevant PRD-3 capability
  assignments and ADRs to record this explicitly approved exception and stack.
  Keep research visibly early access and PRD-2 quality acceptance open.
- Retain feed/search/item selection as a subsequent small slice, following the
  supplied research's typed `NewsCatalog` boundary and direct-MCP direction.
  Structured citations require a later, separately compatible contract change.

## Capabilities

### New Capabilities

- `browser-research-ui`: Secretless browser sign-in, bounded live research,
  inert cited answers, accessible core controls and verified ACA delivery.

### Modified Capabilities

- `a2a-serving`: Add exact-origin browser preflight and response handling while
  retaining existing nonbrowser clients and all authentication/task boundaries.
- `agent-evaluation`: Preserve historical production-input pins and recognize
  a separately pinned UI-workspace manifest without accepting stale approvals.

## Impact

Owning documents: [PRD-3](../../../docs/prd-3.md) slice 3.1 and
[capabilities](../../../docs/prd-3-capabilities.md) P3-C01/P3-C06 plus the minimal
chat, citations and accessibility portions of P3-C02/P3-C03/P3-C05.
Prerequisites are the delivered PRD-2 transport, OBO and research runtime.
The approved sequencing exception does not satisfy P2-C06 or full PRD-3 acceptance.

Planned implementation surfaces are `services/web`, root npm workspace/lockfile
and checks, agent ingress/tests, owning platform preparation/readback helpers,
`infra/ui-identity`, `infra/ui`, `infra/agent`, `azure.yaml`, and a UI runbook.
Only necessary frontend dependencies enter this slice; MCP JavaScript dependencies,
feed caching and broader navigation wait for the catalogue slice.

New authority is limited to the SPA's agent permission and the UI workload's own
registry-pull role. No database/model/MCP role, new model, new Azure environment,
deployment key, standing user identity or application-only research access.
The existing models and region remain unchanged. Exact SDK wire compatibility,
scoped registration/consent readiness and the UI replica/cost profile must be
verified before deployment; npm version existence is not live compatibility.

The user separately approved the primary-gate compatibility fix after its
manifest pin rejected the necessary uv exclusion. Only that exact new root
manifest is added as another known input set. Historical hashes and serialized
provenance remain unchanged; unknown manifests and old approvals against new
source still fail. This does not authorize an evaluation run or budget reset.

Out of scope: baseline retries/publication, archival of incomplete evaluations,
structured A2A output, feed/search/paging, persistent chat or preferences,
curator/admin features, cached HTTP API, private networking, automatic CI
deployment, and a copy of the research handoff.
