# PRD-3 capabilities: Agent UI

This document owns behavior, user stories, acceptance criteria, and future-work
boundaries. [PRD-3](prd-3.md) owns phase status, prerequisites, and the delivery plan.
See [the ADRs](adrs.md) for shared architectural decisions.

## P3-C01: Browser sign-in with organizational identity

**Outcome:** A person can access the research agent from an authenticated browser UI.

**User stories**
- **P3-C01-US1:** As a news reader, I want to sign in with my Entra account
  so that I can use the agent without managing an application password or API key.
- **P3-C01-US2:** As an identity administrator, I want browser access to preserve
  the delegated user flow so that the UI does not introduce shared agent access.

**Acceptance criteria**
- The UI uses MSAL for Entra sign-in.
- Agent requests carry the signed-in user's access token through the Phase 2
  delegated-access design; the UI does not substitute a standing application identity.
- No passwords, keys, or client secrets are introduced.
- A signed-in user receives an agent answer from the deployed browser application.

## P3-C02: Streaming research chat

**Outcome:** Readers can ask news questions and see the agent's response as it arrives.

**User stories**
- **P3-C02-US1:** As a news reader, I want to ask research questions in a chat
  interface so that I do not need to operate an A2A client myself.
- **P3-C02-US2:** As a news reader, I want streamed answers so that I can begin
  reading while the response is being produced.

**Acceptance criteria**
- The browser communicates with the Phase 2 agent rather than creating a separate
  research/model pipeline.
- Chat renders the agent's streamed responses.
- No-match and refusal responses remain visible as agent responses rather than
  being replaced by invented successful answers.
- Streaming is verified manually and through Azure browser end-to-end tests.

## P3-C03: Visible, navigable article citations

**Outcome:** Readers can move from the agent's explanation to its original sources.

**User stories**
- **P3-C03-US1:** As a news reader, I want clearly visible citations alongside
  the answer so that I can distinguish sourced reporting from an unsupported claim.
- **P3-C03-US2:** As a news reader, I want to follow a citation to the original
  article so that I can inspect its context and attribution.

**Acceptance criteria**
- Citations supplied by the agent are visible in the chat experience.
- Following a citation navigates to its original article URL.
- Citation labels and article-derived strings are rendered as inert text, not
  executable publisher-supplied markup.
- The deployed sign-in, chat, and citation-navigation path passes end-to-end tests.

## P3-C04: Source, category, and date shortcuts

**Outcome:** Readers can narrow their research without manually writing every constraint.

**User stories**
- **P3-C04-US1:** As a news reader, I want source and category shortcuts so that
  I can focus the agent on publishers or topics relevant to me.
- **P3-C04-US2:** As a news reader, I want date shortcuts so that I can ask about
  a chosen time period without repeatedly typing date instructions.

**Acceptance criteria**
- The UI provides basic shortcuts for source, category, and date.
- Selected shortcuts become instructions to the agent; they do not introduce a
  separate browser-to-database or model access path.
- Manual Azure checks verify that selected constraints reach the agent, and
  browser tests cover the resulting interaction.

## P3-C05: Inert rendering and accessibility basics

**Outcome:** The news interface remains usable without executing untrusted content.

**User stories**
- **P3-C05-US1:** As a news reader, I want news-derived and agent-provided strings
  displayed safely so that article content cannot execute code in my browser.
- **P3-C05-US2:** As a keyboard or assistive-technology user, I want accessible
  basic controls so that I can sign in, ask questions, and follow citations.

**Acceptance criteria**
- All displayed strings are inert text; untrusted content is not interpreted as
  executable HTML or script.
- Tests exercise hostile content in chat, citations, and filter-related text.
- Accessibility basics cover labelled controls and keyboard operation of the
  core sign-in, chat, filter, and citation interactions.
- Browser tests run against the deployed Azure UI.

## P3-C06: Supported UI integration and verified Azure hosting

**Outcome:** Maintainers can deploy a browser experience backed by a deliberately
chosen, compatible agent integration.

**User stories**
- **P3-C06-US1:** As a maintainer, I want the framework and transport validated
  in a short spike so that the UI integrates with the existing agent rather than
  forcing an untested architecture.
- **P3-C06-US2:** As a maintainer, I want the complete browser journey tested in
  Azure so that the delivered UI is proven beyond a local demonstration.

**Acceptance criteria**
- Compare CopilotKit with AG-UI against a plain JavaScript framework with an A2A
  client, and record the framework/transport decision in an ADR.
- Host the selected UI on ACA and deploy through the existing Terraform/azd workflow.
- Verify a signed-in user can chat, receive a streamed answer, and follow citations.
- Azure end-to-end and accessibility checks pass before phase acceptance.

## Boundaries and decisions still required

The spike owns the framework/transport decision; no framework is selected here.
Private networking, an edge, curator tooling, budgets/alerts, automatic CI
deployment, and retention/privacy policy remain later PRDs. These capabilities
do not add account management, saved chat history, or news-editing features.
