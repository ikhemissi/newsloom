# PRD-2 capabilities: A2A research agent

This document owns behavior, user stories, acceptance criteria, and open product
decisions. [PRD-2](prd-2.md) owns phase status, prerequisites, and the delivery plan.
See [the ADRs](adrs.md) for architecture.

The [agent runbook](agent.md#actual-model-stage-azure-acceptance) records actual
runtime evidence for P2-C01/P2-C02; [PRD-2](prd-2.md) owns delivery status.
This demonstrator does not establish P2-C03-P2-C06 research or quality acceptance.
The separate [research receipt](agent.md#state-constrained-actual-acceptance)
records local and signed-in checks for P2-C03-P2-C05. Those focused cases do not
establish P2-C06's frozen phase-wide quality baseline; [PRD-2](prd-2.md) owns
release status.

## P2-C01: Discoverable, streaming A2A access

**Outcome:** Compatible clients can discover and converse with the research agent.

**User stories**
- **P2-C01-US1:** As an A2A client developer, I want an agent card and A2A endpoint
  so that my client can discover and invoke the news research agent.
- **P2-C01-US2:** As a signed-in researcher, I want streamed responses so that
  I can follow an answer as it is produced.

**Acceptance criteria**
- A Microsoft Agent Framework Python app exposes an A2A endpoint and agent card.
- The agent runs on ACA, uses Foundry models, and supports A2A streaming.
- The endpoint validates the caller's Entra token before serving authenticated
  research requests.
- A signed-in A2A client can invoke the deployed agent.

## P2-C02: Secretless access on behalf of the user

**Outcome:** MCP always sees the signed-in user, not a standing agent identity.

**User stories**
- **P2-C02-US1:** As a researcher, I want the agent to use my delegated MCP
  permissions so that research does not bypass my access boundary.
- **P2-C02-US2:** As an identity administrator, I want a secretless token exchange
  so that the agent requires no client-secret storage or rotation.

**Acceptance criteria**
- The caller supplies an Entra token; the agent exchanges it on behalf of the
  user for an MCP token rather than forwarding an inappropriate token.
- The agent holds no standing MCP access of its own.
- A federated managed-identity credential supports the exchange without passwords,
  keys, or client secrets; this is verified in Azure, not assumed.
- Failure of delegated access does not fall back to application-only access.
- A signed-in A2A client calls one MCP tool through the agent with the user's
  identity preserved.

## P2-C03: Multi-step research grounded in curated news

**Outcome:** Researchers can investigate changes and compare sources using stored news.

**User stories**
- **P2-C03-US1:** As a researcher, I want to ask what changed in agent frameworks
  this week so that I can understand developments across several news items.
- **P2-C03-US2:** As a researcher, I want the agent to compare reporting from
  different sources so that I can understand where their accounts agree.
- **P2-C03-US3:** As a reader, I want explanations of one or multiple selected
  items tailored to my stated audience, language, detail and focus preferences.

**Acceptance criteria**
- The agent can make multiple relevant MCP calls to discover sources, retrieve
  recent items, search within filters, and inspect selected stored items.
- Answers are grounded in MCP results only, not unsupported model recollection
  or an independent web-fetching path.
- Research remains read-only and does not modify news, feed configuration, or jobs.
- Preferences supplied in the current request guide presentation without
  overriding evidence, filters or access controls; no persistent memory is implied.
- Explanations distinguish what the stored summaries support from detail absent
  from the collection; a detail lookup is not full-article or web access.
- Manual scenarios and frozen questions cover multi-step research and tool use.

## P2-C04: Cited answers and explicit lack of evidence

**Outcome:** Readers can verify an answer and recognize when the curated collection
cannot support one.

**User stories**
- **P2-C04-US1:** As a researcher, I want original article URLs cited in answers
  so that I can inspect the evidence behind the agent's conclusions.
- **P2-C04-US2:** As a researcher, I want an explicit no-match answer when relevant
  news is absent so that a plausible invention is not mistaken for evidence.

**Acceptance criteria**
- News claims cite URLs of the supporting MCP items.
- Citation correctness and groundedness are evaluated against the retrieved items.
- When no matching evidence exists, the agent says so rather than fabricating
  news, sources, or citations.
- The frozen question set includes supported research and no-match cases.

## P2-C05: Resistance to instructions embedded in news

**Outcome:** Research stays within the user's request even when retrieved text is hostile.

**User stories**
- **P2-C05-US1:** As a researcher, I want article text treated as data so that
  a publisher cannot redirect the agent away from my request.
- **P2-C05-US2:** As a platform operator, I want the research agent restricted
  to read-only behavior so that injected instructions cannot authorize mutations.

**Acceptance criteria**
- News text cannot override agent instructions, the user request, or access controls.
- The agent never follows instructions embedded in news or treats them as tool
  authorization.
- Injection scenarios exercise retrieved content as well as normal research paths.
- Credentials, article text, prompts, and completions are excluded from telemetry,
  following the shared observability decision.

## P2-C06: Repeatable agent quality and Azure acceptance

**Outcome:** Maintainers have evidence that research remains useful, grounded,
and correctly delegated as the agent changes.

**User stories**
- **P2-C06-US1:** As a maintainer, I want a frozen question set and baseline report
  so that I can compare research quality across changes.
- **P2-C06-US2:** As a maintainer, I want deployed identity and tool-use checks
  so that local success is not mistaken for working Azure integration.

**Acceptance criteria**
- Evaluations cover groundedness, citation correctness, tool-use correctness,
  injection cases, and secretless OBO.
- Preserve an evaluation report as the baseline.
- A signed-in A2A client receives cited answers to multi-step questions in Azure,
  and the frozen question set passes its defined evaluation criteria.
- Repository release gates follow the
  [OpenSpec delivery contract](../openspec/specs/repository-foundation/spec.md#requirement-honest-ordered-delivery).

## Decisions still required

The feasibility gate in [P2-C02](#p2-c02-secretless-access-on-behalf-of-the-user)
is verified in Azure; see the [live delegation receipt](agent.md#status-and-scope).
Define frozen questions and evaluation pass criteria when implementing P2-C06.
The user's preferred Step 2.3 direction is DeepEval combined with Microsoft
Foundry evaluations, with run results visible in Foundry's evaluations experience.
Offline and online quality evaluation, cost management and governance are
primary project priorities. The delivered interoperability
[evaluation foundation](agent-evaluation.md#status-and-scope) has verified
isolated Python/SDK compatibility, secretless judging, exact imported-score
API/user-attested UI parity, evaluation storage and disposable lifecycle.
Its two authored precomputed answers do not establish this capability's frozen
deployed-agent baseline. The foundation's
[owning ledger](../openspec/changes/agent-evaluation-foundation/tasks.md) records
its separate implementation, measured-status and completion CI.
Define evaluator calibration, sampling, content privacy, retention and spend
limits for the subsequent quality slices. Define an iterative improvement loop:
classify failures, change one agent component, compare candidates against a
versioned baseline for quality and cost, approve only passing candidates, and
use online signals to propose reviewed regression cases rather than
automatically changing the agent or ingesting production content.
UI-specific transport selection belongs to
[P3-C06](prd-3-capabilities.md#p3-c06-supported-ui-integration-and-verified-azure-hosting).
