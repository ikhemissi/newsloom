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
  following progress before the validated final answer is ready.

**Acceptance criteria**
- The browser communicates with the Phase 2 agent rather than creating a separate
  research/model pipeline.
- Chat renders the agent's streamed progress and validated final response.
  The existing backend does not stream unvalidated draft tokens.
- Each question is independent; transient UI history does not imply agent memory.
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

**Assignment:** active [`ui-news-filters`](../openspec/changes/ui-news-filters/tasks.md),
deployed early access with local/owning deployment checks passed and regular-browser/
automated signed-in Azure acceptance still open; not full phase acceptance.

**Outcome:** Readers can narrow their research without manually writing every constraint.

**User stories**
- **P3-C04-US1:** As a news reader, I want source and category shortcuts so that
  I can focus the agent on publishers or topics relevant to me.
- **P3-C04-US2:** As a news reader, I want date shortcuts so that I can ask about
  a chosen time period without repeatedly typing date instructions.

**Acceptance criteria**
- The UI provides basic shortcuts for source, category, and date.
- Source/category choices use exact catalogue IDs; Any time is the default.
  Today, Last 7/30 days and custom inclusive dates use local calendar arithmetic
  with UTC-aware inclusive lower/exclusive upper bounds.
- Draft edits dispatch nothing. Apply retains the submitted query; Search submits
  the draft query and filters together. Reset preserves the submitted query;
  clearing search preserves applied filters. Query-less metadata search has no
  inference cost.
- Applied shortcuts become structured ResearchRequest filters, not appended prompt
  instructions or a separate browser-to-database/model path. Each explicit
  question and its answer retain an immutable visible context snapshot.
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

The approved [stack decision](adrs.md#ui-stack-comparison) selects plain React,
official A2A and MSAL with ACA hosting; the bounded compatibility spike and
deployed browser acceptance are still required. Existing text citations stay
unchanged; structured citation output needs a separately compatible change.
Private networking, an edge, curator tooling, budgets/alerts, automatic CI
deployment, and retention/privacy policy remain later PRDs. These capabilities
do not add account management, saved chat history, or news-editing features.

## P3-C07: News feed, search and item context

**Status:** latest-feed/search/context slice deployed as early access in
[`ui-news-feed`](../openspec/changes/ui-news-feed/tasks.md). The user confirmed
the regular-browser journey; implementation/status publication is verified and
full automated acceptance remains pending. Filters belong to the active
[`ui-news-filters`](../openspec/changes/ui-news-filters/tasks.md) slice. Detail
routing and capped browsing pagination belong to the active
[`ui-http-news-catalog`](../openspec/changes/ui-http-news-catalog/tasks.md)
migration over the deployed API contract; multi-selection remains subsequent work.

**Outcome:** Readers can browse stored news and explicitly choose research context.

**User stories**
- **P3-C07-US1:** As a reader, I want recent news and submitted semantic search
  so that I can find relevant stored reporting.
- **P3-C07-US2:** As a reader, I want an item page and bounded selection
  so that the agent can research the items I chose.

**Acceptance criteria**
- Browser news access uses a typed NewsCatalog boundary, initially backed by
  read-only MCP with the user's separate delegated `news.read` token.
- The HTTP migration uses GET news/sources/detail and explicit POST semantic
  search while retaining delegated `news.read`. Errors remain distinct from
  empty results; browser MCP fallback is not permitted.
- The default page shows the latest 20 stored items without a hidden date cutoff.
  A top search box shows bounded relevance-ranked results and clears to latest news.
- Agent interactions use A2A in a closable right-side panel, closed by default.
  Selecting news supplies visible removable context; opening/searching alone
  never submits research. Closing/reopening does not replay work.
- Shareable `/news/<uuid>` pages show stored summary/metadata, safe original
  links and explicit item context, not fetched full articles. Browser history and
  Back to news preserve transient browsing without research replay.
- Item context and up to five selected distinct IDs reach the existing agent
  request contract; no browser database/model access is added.
- Direct MCP requires its own exact-origin CORS, consent, protocol compatibility
  and multi-user capacity checks before deployment.
- Browse/metadata Load more requests 20 per click, capped at 200 displayed items
  with an explicit restart. Semantic search remains top 20 without paging.
  The display cap is not server exhaustion, and live keysets are not a snapshot.
- The active [`cached-news-api`](../openspec/changes/cached-news-api/tasks.md)
  backend slice owns 60-second process-local response caching and browse-only
  keysets; semantic search stays bounded to 50. It does not deliver browser paging
  or switch the NewsCatalog adapter. Richer citations/history remain future work.

## P3-C08: Shared daily weekly-news briefing

**Assignment:** active
[`daily-news-briefing`](../openspec/changes/daily-news-briefing/tasks.md);
implementation and acceptance tracked there, not a completed phase.

**Outcome:** Readers can scan a shared weekly overview without asking a question.

**User stories**
- **P3-C08-US1:** As a reader, I want a daily five-minute overview of the last
  seven days so that I can catch up without repeatedly requesting research.
- **P3-C08-US2:** As a reader, I want a visible TL;DR and a collapsed cited
  summary so that I can choose how much detail to read without crowding the panel.

**Acceptance criteria**
- Generate once daily at 05:00 UTC from the preceding seven-day stored-news
  snapshot, independent of filters or selected articles; exclude the cutoff.
- The [architect-focused refinement](../openspec/changes/architect-focused-briefing/tasks.md)
  prioritizes concrete architecture-relevant changes, excludes routine news and
  permits shorter output without padding. Combined TL;DR/narrative is at most
  1,000 words (estimated five-minute ceiling); no-material/empty states differ.
  Legacy published artifacts remain readable under their historical policy.
  Derive the TL;DR from the completed summary in the same run and atomically
  publish one version with safe original-source citations.
- Place the TL;DR above a full-summary collapsible closed by default at the top
  of the Agent panel. Preserve composer/answer context and independent scrolling.
- Read through existing delegated news.read without generating on reads or
  expansion. MCP stays read-only; the scheduler uses a dedicated writer identity.
- Show generation time before the TL;DR, with concise exceptional state notices.
  Retain actual window/cutoff metadata in the protected operational contract. Measure
  model usage/cost without an initial daily spending cap.
- Verify actual scheduled execution separately from bootstrap and record
  real signed-in Azure accessibility/behavior, leaving unavailable checks open.

See the [briefing runbook](briefing.md) for operations and measured evidence.
