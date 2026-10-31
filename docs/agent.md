# Agent skeleton runbook

## Status and scope

[Step 2.1](prd-2.md) is complete and verified. Its
[archived change checklist](../openspec/changes/archive/2026-10-27-agent-skeleton/tasks.md) owns delivery
progress. Local package/protocol compatibility, the agent's separate authorization policy,
request-local delegated adapters and the non-generative authenticated A2A
application are verified locally, as are the opt-in owning layers with mocked
providers, package-only container and explicit PKCE acceptance client.
The owning identity layer is provisioned with independently verified federation,
delegated consent and narrow grants. The immutable non-generative agent app is
deployed with independently verified configuration and public authorization
guards.
Actual browser sign-in, secretless OBO, a user-preserving MCP read and the
required live workload denials have passed. Task 3.2's live gate is complete.
The model-backed revision is now deployed with verified local and Azure runtime
acceptance: actual signed-in streaming, cancellation, authenticated private
telemetry and final workload/data preservation. See the
[live model-stage receipt](#actual-model-stage-azure-acceptance).
Implementation publication and the separate evidence/status receipt passed
their own exact-SHA CI; see the
[publication receipt](#verified-implementation-publication) and
[final delivery receipt](#verified-evidencestatus-delivery).
At that delivery, all 15 tasks were verified and only Step 2.1 was accepted.
Its OpenSpec change is
archived with the delivered A2A/delegation contracts synchronized to main specs.
Research is delivered separately below; the browser UI remains a later slice.

Step 2.2 local implementation, the research-enabled owning deployment, actual
signed-in research, semantic/citation review, cancellation, private telemetry and
preservation are verified under the
[research checklist](../openspec/changes/archive/2026-10-28-agent-research/tasks.md).
See the [actual receipt](#state-constrained-actual-acceptance).
Implementation and separate evidence/status publication passed exact-SHA CI;
[Step 2.2 is delivered](#verified-research-delivery). A ready deployment alone
was not treated as completed research delivery.

This runbook owns commands and measured implementation facts, not another
requirements copy. See the
[archived design](../openspec/changes/archive/2026-10-27-agent-skeleton/design.md),
[A2A serving contract](../openspec/specs/a2a-serving/spec.md) and
[delegation contract](../openspec/specs/delegated-mcp-access/spec.md).

## Research request contracts

The additive [research DTOs](../services/agent/src/newsloom_agent/research_models.py)
are independent of the MCP server package. The research A2A request contains one
JSON data part, for example:

```json
{
  "operation": "research",
  "question": "Compare the selected announcements for an engineering audience.",
  "item_ids": ["<stored-item-uuid>"],
  "filters": {
    "tags": ["agents"],
    "from": "2026-10-20T00:00:00Z",
    "to": "2026-10-28T00:00:00Z"
  },
  "preferences": {
    "language": "English",
    "audience": "Engineers",
    "detail": "detailed",
    "focus": "Operational implications supported by the stored summaries"
  }
}
```

Replace `<stored-item-uuid>` with a real stored item's UUID kept in private
request input; the placeholder is not itself a valid request value.
Selection is optional; when supplied it must contain one to five distinct UUIDs.
Questions and language/audience/focus preferences have respective UTF-8 byte
ceilings of 8,192 and 64/256/1,024; blank or invalid UTF-8 strings fail.
Dates require explicit timezone-aware timestamps, normalize to UTC and use an
inclusive lower/exclusive upper interval. Tags are whitespace-normalized,
case-folded and deduplicated, with the same vocabulary rules as MCP.
Unknown fields, invalid intervals and unsupported detail values fail validation.
Preferences are request-local presentation hints, not permission or memory.

Tool plans have only the four fixed MCP operation names and locally owned
argument/result shapes. Research recent/search results allow at most five items;
the original one-item `RecentNews` DTO is unchanged. Detail adds author, date
origin and publisher categories, not full article text. Explicit not-found is
different from a malformed result or failed read.

The final contract contains outcome, supported claims with evidence IDs,
limitations, missing selected IDs and coverage, never model-selected citation
URLs. Contract validity alone does not establish semantic support or safe
delivery: evidence membership, exact stored URLs, selection coverage and rendered
size still require controller validation before emission. No web, full-article,
persistent-memory or phase-wide evaluation capability is implied.

Local contract validation: **51 focused cases passed**, plus **54 existing
delegation cases**; strict types and focused lint passed. All **13 OpenSpec
items** passed strict validation. These are local results with authored fixtures,
not model-quality scores or Azure research acceptance.

### Research delegated session

The [delegation adapter](../services/agent/src/newsloom_agent/delegation.py)
shares only the original OBO validation and fixed-endpoint transport mechanics
with recent-news. A research request exchanges once, checks the exact same user,
agent client and `news.read` scope, then owns one initialized MCP SDK session.
Its lifetime is bounded by the original caller deadline and exchanged-token
expiry, including time between operations. Every exit closes the HTTP/session
and OBO credential; no session, discovery set or token is reused by another user.

Locally typed calls support all four existing tools. Detail IDs must be selected
or discovered in this request. Selected mode refuses discovery operations;
not-found stays explicit and another record cannot replace the requested ID.
Identical repeated calls and a ninth operation fail before dispatch.
Transport accounting enforces the unchanged 128 KiB per-response bound and a
512 KiB aggregate, including initialization, without resetting between calls.
Caller-filter enforcement and evidence consistency remain controller work, not
an added permission on the agent.

Local validation passed **162 cases** covering research contracts/delegation,
original delegation and MCP authorization/HTTP, plus strict types across **14
agent source files**. The multi-call tests exercise the official MCP SDK against
the local HTTP MCP application, not Azure. Research remains unavailable on A2A
until its controller and default-off serving/configuration wiring are complete.

### Structured research connector

The [research connector](../services/agent/src/newsloom_agent/research_generation.py)
uses the same pinned `OpenAIChatCompletionClient`, fixed endpoint/deployment,
managed-identity bearer and no-retry HTTP client as recent-news. It sends
non-streaming chat-completions requests with `store=false`, no tools and strict
application-owned JSON schemas. SDK automatic tool execution is not enabled.
Local schema normalization makes closed object properties required, translates
the tool union to `anyOf`, and removes schema defaults/discriminators; application
DTO validation remains authoritative. No request or model output chooses a
schema, endpoint, credential or executable function.

Research admits at most three 512-token planning calls and one 2,048-token
synthesis, reserving final capacity before planning. Exact serialized HTTP input
is bounded to 64 KiB per call / 256 KiB aggregate, including instructions and
schema; raw responses retain 128 KiB per call / 512 KiB aggregate. The aggregate
output ceiling is 4,096 tokens. All calls use the delegated request deadline.
Usage totals accumulate only observed provider values; an unfinished call
invalidates complete-usage coverage rather than inventing zero consumption.
Malformed, refused, incomplete, unmetered or out-of-budget results fail without
repair generation or another provider.

Local structured/recent-news connector validation passed **56 cases**, including
actual request/response byte boundaries through the pinned transport and
unchanged recent-news streaming. Strict types passed for the changed connector
and test modules. This verifies local wire compatibility, not a live provider
quality score or Azure research acceptance.

### Research evidence controller and answer validation

The [controller](../services/agent/src/newsloom_agent/research.py) bootstraps
selected details before planning, or admits bounded discovery plans. Each request
owns immutable filters, its call history, source discovery and at most ten unique
metadata/detail records. It refuses dropped/broadened caller constraints before
dispatch and checks returned records against both caller and planned filters.
Selected records outside hard filters fail rather than broadening or silently
discarding the constraints. Conflicting metadata/detail versions, foreign IDs,
repeated operations and aggregate overrun are explicit failures, not truncation.

Only current detail records can support final citations. Discovery metadata alone
cannot become a cited full-detail answer. Healthy empty retrieval has an explicit
no-match response without final synthesis; a model cannot claim absence without
any news retrieval, or turn a failed read into model-recollection success.
Missing selected IDs and retrieval coverage are application-checked and rendered
explicitly. Three planning turns retain a separate final-call reservation.

The answer renderer resolves IDs to exact stored HTTPS URLs, refuses credentials,
literal/encoded controls and model-authored replacement links, and bounds the
complete UTF-8 answer plus citations and fixed evidence limitations to 16 KiB.
Progress contains only fixed phases and safe counts. No draft answer is yielded
before validation. Authored claim/evidence cases check supported single/multi-item
statements separately from the structural/provenance checks; neither establishes
the future phase-wide semantic baseline.

Local component verification passed **237 cases** across research, original
delegation/generation and real-HTTP privacy canaries, with strict types across
**18 source/test files** and focused lint. A regression that disabled deliberately
forced framework instrumentation inside the shared transport was caught by the
existing privacy canary and corrected; the exporter is still exercised with
actual sensitive automatic spans. Research serving/deployment acceptance remains
pending.

### Research A2A delivery and client

The enabled service accepts one `application/json` data part using the research
contract above. Its card adds `research` and JSON input alongside `recent-news`.
Disabled research is absent from discovery and rejected before delegation or
inference. Unsupported fields, attachments, extra parts and malformed inputs
remain failures, not an invitation to interpret arbitrary conversation history.

Research streams fixed progress phases/counts first. The model's plans and final
draft are buffered privately; only the validated rendered answer becomes artifact
chunks. This is **not live draft-token streaming**. Completed task readback must
match the collected artifacts exactly. Read/list/cancel/context ownership and
the original recent-news operation retain their existing controls.

With the existing ignored acceptance-client environment configured, supply one
bounded request on standard input:

```bash
printf '%s' '{"operation":"research","question":"Explain the most recent stored news.","preferences":{"detail":"brief"}}' \
  | uv run --locked newsloom-agent verify-research
```

The command performs the existing browser PKCE flow for `news.agent`, uses the
official A2A client and reports only bounded acceptance counts. It does not print
the question, preferences, answer or citations. It rejects input above 64 KiB
before authentication. The CLI is an operator verifier, not a persistent chat UI.

Local validation passed **197 cases** across research A2A/client/telemetry,
runtime/operator, original A2A/client and real-HTTP privacy tests. The research
cases include an actual loopback official client, actual delegated MCP SDK/local
HTTP and pinned structured model transport, validated readback, invalid citation
failure, caller isolation, default-off admission and bounded stdin. Strict types
passed across **19 source/test files**; package-only startup passed. These remain
local authored responses, not Azure research or semantic-quality acceptance.

### Research configuration and usage observations

The [coverage correctness slice](../openspec/changes/research-answer-scope-fix/proposal.md)
binds synthesis coverage and missing-item IDs from typed controller state,
using the same trusted-scope pattern as planning. Its final response schema
permits only the actual coverage value and missing-ID membership/count.
Untrusted context cannot select these controls, and independently inconsistent
provider output still fails without being rewritten or retried. Existing
no-match, selection/filter, citation, deadline and token limits remain intact.
The targeted local generation/controller/A2A/capture selection passes 148 tests,
including all four coverage modes and wrong/foreign/duplicate provider values.
These local results do not establish a new deployed image or full quality
baseline; those gates remain in the owning slice ledger.

The subsequent approved agent-only deployment changed zero resource counts
and only the existing image/runtime revision. Its new source is
`994707f93566db4f67d8d79aff1116ace2d763776d3775a41de835568a4dc60c`
and immutable image digest is
`7cac78479b9c3c755e527e4a4986015ecbb3e46610c721bfd53c23930868e337`.
After initial rollout lag, the owning image/configuration readback passed.
The first live discovery check expired during sign-in at the user's availability
deadline, before generation; that attempt is retained. A subsequently resumed,
bounded same-user discovery check passed against the new image: supported
outcome, one evidence item, two tool calls, four generation/usage calls, 4,743
input and 373 output tokens. Pre/post item/pool fingerprints and streamed/
completed-task parity matched; final validation establishes discovery coverage.
Estimated chat cost was USD 0.005759325, with embedding exposure reserved
separately. No answer/news text or judge reason was saved. This is narrow
coverage acceptance, not full quality-baseline or live injection acceptance.
Implementation publication passed its
[exact-source primary CI](https://github.com/ikhemissi/newsloom/actions/runs/41197276231)
at `af108f171b60a757fbc3c18aaed335997a457aa9`. Separate measured-status
publication/CI remains open in the [owning ledger](../openspec/changes/research-answer-scope-fix/tasks.md).
The failed baseline and its original accepted image are not relabelled.

`AGENT_RESEARCH_ENABLED` defaults to `false`; only exact `true`/`false` values are
accepted. The owning app's separate `research_enabled` input injects the same
setting. Enabling research does not add resources, identities, permissions,
models or replica capacity. It requires the already enabled agent app.
Public discovery/startup acquires no identity tokens in either mode.

After the complete local gate and retained-environment inventory, the user's
standing Step 2.2 authorization permits the following owning update. Review the
exact preview before applying; do not provision another layer:

```bash
AZURE_DEV_USER_AGENT=microsoft_foundry_skill azd env set AGENT_RESEARCH_ENABLED true
AZURE_DEV_USER_AGENT=microsoft_foundry_skill uv run --locked newsloom-platform build-agent
AZURE_DEV_USER_AGENT=microsoft_foundry_skill azd provision agent --preview --no-prompt
# Continue only for the reviewed immutable agent app/configuration change:
AZURE_DEV_USER_AGENT=microsoft_foundry_skill azd provision agent --no-prompt
AZURE_DEV_USER_AGENT=microsoft_foundry_skill uv run --locked newsloom-platform verify-agent
```

To disable only research while retaining recent-news, set the flag to `false`,
review the same app-only preview and apply it without rebuilding or provisioning
identity/shared layers:

```bash
AZURE_DEV_USER_AGENT=microsoft_foundry_skill azd env set AGENT_RESEARCH_ENABLED false
AZURE_DEV_USER_AGENT=microsoft_foundry_skill azd provision agent --preview --no-prompt
AZURE_DEV_USER_AGENT=microsoft_foundry_skill azd provision agent --no-prompt
AZURE_DEV_USER_AGENT=microsoft_foundry_skill uv run --locked newsloom-platform verify-agent
```

Immutable source binding still applies. For full app removal or a prior matching
image/source, follow [agent-only recovery](#failure-disable-and-compatible-rollback).
These are documented recovery paths, not a claimed live rollback drill.

Research telemetry uses operation `research`, bounded aggregate generation/tool
counts, observed input/output token totals, `usage_observed_calls` and
`usage_complete`. If cancellation interrupts the fourth call after three metered
turns, the three known usages remain counted while complete coverage is false;
unknown consumption is never recorded as a metered zero. Recent-news keeps its
original single-call token limits. No question, preference, plan, news, URL,
draft, answer or credential is added to diagnostic attributes.
Mocked-provider validation passed **15 owning app cases**, including default-off
and enabled research without widening the existing 0.25 CPU/0.5 GiB profile.

### Verified coverage-contract correction

The scoped implementation and the independently reverified image remain
source-matched. After implementation CI passed, this separate measured-status
publication records the successful discovery case and preserved failures.
Its own exact-source CI is pending; the narrow fix is not fully delivered
until that publication gate passes. Whole-baseline semantic scores, Foundry
report/UI parity and broader PRD-2 completion remain unverified.

Across the retained evaluation attempts and successful coverage check, observed
chat token cost is estimated at USD 0.039391275. Separately reserved unknown
chat/embedding exposure totals USD 0.958144512, giving conservative model
exposure USD 0.997535787 against the user's USD 100 allowance. Reservations
are not measured spend, and registry-build/runtime/log costs are not metered
by this token report. Prior approvals, expired callbacks and failed captures
remain retained rather than relabelled or repaired.

### Research privacy and cancellation

The local HTTP canaries exercise hostile stored text and preferences, invalid
plans/citations, OBO/MCP/provider failures, expired delegation, overload and four
disconnected callers. Both disabled and deliberately forced sensitive framework
instrumentation are exercised through actual exporters; absence of spans alone
is not treated as privacy evidence. Exported diagnostics retain only fixed
categories and bounded counts, never request/evidence/model content or tokens.

Cancellation is checked during exchange, MCP, planning, final synthesis,
progress, validation and artifact emission. A controlled stalled HTTP writer
fills the actual eight-event queue; explicit cancellation, disconnect and
failure must still await cleanup and retain a non-completed terminal task.
The final task snapshot reports cancellation/failure even when its duplicate
status notification cannot fit in a full queue.

These tests found and fixed two real lifecycle faults: MCP task groups wrapped
normal suspended-generator closure in nested exception groups, and a terminal
cancellation notification could block behind a full queue. Normal closure is
now normalized after SDK teardown without hiding concurrent failures; terminal
failure/cancellation cannot wait for space in a stalled output queue.
Local validation passed **163 lifecycle/HTTP/delegation cases**, followed by
**22 privacy/usage cases** including the additional stalled failure/disconnect
checks. All request-owned sessions/transports close before cancellation returns.
This is local transport evidence, not deployed cancellation acceptance.

### Complete research local gate

The complete PostgreSQL-enabled `bash scripts/check.sh` gate and
`uv build --all-packages` passed on 2026-10-27:

- **1,213 tests passed**, with only the intentional live-publisher skip.
- **131 files** passed strict types; **222 files** passed formatting and lint.
- All six packages produced source archives and wheels; isolated runtime
  startup, feed configuration and identifier checks passed.
- All **13 OpenSpec items**, ten Terraform layer validations and their
  **71 mocked-provider cases** passed.
- Earlier attempts caught literal UUID examples and test-file Terraform
  formatting. Both were corrected without weakening either check.

Four actual local HTTP research requests ran concurrently with ten evidence
records, seven tool operations and four model calls each. Questions and
preferences used their byte ceilings; the largest serialized model input was
**61,496 bytes**, and completed requests consumed **510,482 aggregate raw model
response bytes**. Three completed; one disconnected during final synthesis and
remained cancelled with incomplete usage explicitly identified.
The same measured run exercised full-queue cancellation/failure/disconnect.
Peak local process RSS, including the test runner and local MCP/A2A applications,
was **170.20 MiB**, below the required **400 MiB** threshold for the retained
512 MiB profile. No capacity or replica change was made.

The owned PostgreSQL 18/pgvector helper was stopped/removed and its loopback
port independently verified closed. The stress test also probes its closed
A2A port. These are local results, not signed-in Azure research acceptance.
The owning cloud preparation is recorded below; deployment, signed-in research,
semantic/citation review and deployed preservation have separate checklist gates.

### Research owning inventory, immutable build and preview

On 2026-10-27, read-only retained-environment inspection verified **19 resources**,
the **five other workloads**, exact agent and existing workload grants/actions,
directory registrations/ownership/scopes/consents/federation, and all **three
model deployments**. Their images, identities, schedules and actual pipeline
execution histories were retained privately. An independent MCP-identity SQL
read verified **2,091 stored news records** and retained metadata/ID/URL hashes;
it performed no writes or model calls. Schedules remain active, so this is a
time-correlated baseline, not a frozen-data assumption.

France Central still exposes chat-capable `gpt-5.4-mini` version `2026-03-17`,
`DataZoneStandard`, capacity **10**. Shared regional allocated/limit values were
**110/1,000**; the unchanged deployment permits **10 requests and 10,000 tokens
per minute**. Available regional quota does not increase that deployed rate.

The official [Azure retail API](https://prices.azure.com/api/retail/prices)
returned these current USD meters:

| Retained model/SKU meter | Price |
| --- | --- |
| Chat Data Zone input / cached input / output | $0.825 / $0.0825 / $4.95 per million tokens |
| `text-embedding-3-large`, regional `Standard` query embedding | $0.000158 per thousand tokens |

A proposed six-request live envelope reserves at most **24 chat calls**,
**48 MCP operations**, **1,572,864 chat input tokens** and **24,576 output tokens**.
Conservatively treating every tool operation as an embedding search, including
the MCP transport's existing three-attempt maximum and the 8,192-byte query
bound, reserves **144 embedding attempts / 1,179,648 input tokens**. At the
uncached meters this is approximately **$1.61** of model usage, excluding
build/compute and unrelated scheduled work. This is a conservative planning
estimate, not an invoice or prepaid dollar cap; actual acceptance still needs
an enforced case/time envelope, quota-aware pacing and observed usage.
Unobserved cancelled or retried consumption must not be reported as zero.

Under the user's standing Step 2.2 authorization, only `build-agent` ran.
The immutable build input is
`e0acc67e766c1df2e663c1a9319ebd4a56d0f3f2b05bcd06f643003f20a73704`;
its image digest is
`sha256:79972c1b724a9a893edb303d322aa05686a01f1bb7ff8c6f3058258206b0144d`.
Native `azd provision agent --preview --no-prompt` succeeded with **zero
additions, one in-place change and zero deletions**. Independent JSON-plan
review verified that only the agent image, runtime source revision and
`AGENT_RESEARCH_ENABLED=true` change; every other known resource setting is
unchanged. The exact binary plan/configuration and prior compatible deployment
were retained privately. Its SHA-256 is
`d4b5b867cb480b432a99f62ae70ca69af73a0a91f06563b409294e112263e9be`.
No project, toolbox, model, capacity or grant was added. This preview is not an
apply, ready-revision receipt or signed-in research result.

### Research owning deployment readback

The reviewed native `azd provision agent --no-prompt` completed on 2026-10-27:
**zero added, one changed, zero destroyed**. Independent `verify-agent` and ARM
readback verified the latest revision is actually ready, with the reviewed
immutable image/source, exact trusted configuration, sole managed identity,
unchanged probes, ingress, scale and **0.25 CPU / 0.5 GiB** profile.

The public card truthfully advertises both implemented skills and research's
validated delivery mode; liveness passed. Missing and deliberately invalid
bearers both returned **401** with authentication challenges, without tool or
model work. Fresh inventory independently matched all **19 resources**, the
**five other workloads'** images/identities/configuration/schedules, all **three
models** and the model account, every workload grant/custom action, and directory
registrations/consents/federation against the pre-update snapshots.
No project, toolbox, capacity, grant or other workload changed.
The disposable local database helper was stopped/removed and its port verified
closed.

This verifies the owning deployment only: **no signed-in research request or
paid inference was executed by these readbacks**. Actual multi-step user
delegation, semantic/citation review, cancellation, private telemetry and final
data/history preservation remain separate unchecked acceptance gates.

### First signed-in research attempt: acceptance remains open

On 2026-10-27, the bounded six-case client completed browser PKCE sign-in and
executed **one** selected-item request against the research-enabled revision.
The A2A stream completed with validated artifact/readback parity and preserved
the originating user. The independently recovered terminal receipt reports
**one tool operation, two model calls, 2,529 input tokens and 106 output tokens**,
with usage observed for both calls.

The independent acceptance checker rejected the answer because the authored
question requested the entire exact summary, while the request also specified
`detail=brief`. Read-only caller-owned task readback and independent MCP-identity
SQL inspection, without another generation, established that its **151-character
claim is a verbatim contiguous excerpt** of the **405-character stored summary**,
and its citation is the **exact stored URL**. Thus the failure establishes
shortening of an explicit full-summary request, not an unsupported factual claim
or fabricated citation. No production question, summary, answer, URL or token
was persisted by this inspection.

The first failure receipt retained incomplete usage conservatively because
verification stopped before its accounting update. The separate terminal
readback recovered the actual observed totals above; the checker now accounts
for a completed invocation before reviewing its answer. The uncached chat-meter
estimate is **$0.002611125**, not an invoice; the single detail lookup does not
perform query embedding.

The other five live cases were **not executed**, and neither live acceptance
task is checked. The user subsequently confirmed that explicit content and
quotation requirements override presentation hints such as brevity.
The trusted planning/synthesis instructions now express that priority without
changing evidence availability, filters, permissions or budgets. Three focused
wire regressions cover the complete-summary/brief conflict, ordinary brevity and
unavailable full articles. Authored responses prove instruction placement and
typed delivery, not actual model obedience. The subsequent exact-source
deployment and bounded rerun are recorded below. The failed full-summary
instruction is not relabeled as passing. Publication and archival remain blocked.

### Content-priority follow-up: local and owning gates

The confirmed priority rule is implemented in the trusted instructions used by
both structured planning and synthesis. Its three wire tests first failed on
the missing rule, then passed without changing caller controls or generation
limits. **123 focused cases** passed. The amended source passed the complete
PostgreSQL-enabled `bash scripts/check.sh` and all six package builds:
**1,216 tests passed / one intentional live-publisher skip**, **131 strictly
typed files**, **222 formatted files**, **13 strict OpenSpec items**, ten
Terraform validations and **71 mocked-provider cases**. Repeating the four
near-limit concurrency/full-queue cases measured **170.34 MiB** peak RSS.
The owned database helper was stopped/removed and its port verified closed.

Fresh retained-state inventory verified the same **19 resources**, **five other
workloads**, directory/grant boundaries and **three model deployments**; an
independent read-only baseline counted **2,094 news records**. Current regional
model meters and the unchanged **10 requests / 10,000 chat tokens per minute**
deployment limit were rechecked. This does not assume scheduled data froze.

Only the agent was rebuilt. The amended source is
`b94d9a9a207303ffdd682ef62e94932988bf02c5df18dc348eeb83c23f572491`;
the immutable image digest is
`sha256:6abfa97a7612c4c3bd02bb6ca14e9c9156d7afa3255d1031c9c75be9f3da776e`.
The independently reviewed native preview changed **only image and runtime
source revision**, with **zero additions, one in-place change and zero
deletions**. Its privately retained binary plan has SHA-256
`34fd6d718a9a4ee3bb77e09d2b04ed9bbea869c9f44f43b6f5cccca9db3a43db`.
The agent-only native apply succeeded. Initial readiness verification
correctly rejected a latest revision that was not ready yet; image/source,
configuration and profile already matched. After the observed activation delay,
the unchanged full readiness predicate passed, followed by public card/liveness/
authorization guards and independent workload/resource/model/grant/consent/
schedule preservation. No capacity, grant, toolbox, project or other workload
changed.

The next finite live run permits at most **six new requests**. Including the
first attempt's recovered actual usage, the cumulative envelope is **seven
requests, 26 chat calls, 49 tool operations, 1,575,393 chat input tokens and
24,682 chat output tokens**. Query embedding retains the conservative **144
attempts / 1,179,648 tokens** reservation. The current uncached model-meter
estimate remains approximately **$1.61**, not a bill or prepaid cap, and excludes
build/compute/unrelated scheduled work. The runner limits wall time to
**30 minutes**, spaces requests by at least **70 seconds**, and avoids scheduled
pipeline startup/active enrichment before admitting another request. Cancelled
consumption remains unknown when usage is not observed. The exact complete-
summary conflict must pass; no shortened excerpt is accepted in its place.
Final acceptance remains unchecked.

### Content-priority live rerun: comparison check remains blocked

The amended revision's signed-in rerun began at **21:56 UTC on 2026-10-27**.
Its selected single-item case passed the unchanged independent **entire stored
summary** comparison despite `detail=brief`, with the exact stored citation,
same-user delegation and validated artifact/completed-readback parity. It used
**two model calls, one tool operation, 2,563 input tokens and 142 output tokens**.
This is actual model evidence for the priority fix, not an authored fixture.

The second request completed with two selected-item reads and validated
artifact/readback parity, but its independent comparison checker failed the
literal metadata template. Zero-new-inference caller-owned readback and
memory-only independent SQL diagnostics found the expected source/category
values in both individual claims and exact corresponding stored citations.
Both metadata lines lack the requested final period and are one character
shorter than their expected literal templates. The two-record category
comparison matches its expected literal statement. This does not establish
fabricated facts or citations; the strict format failure is retained, not
silently converted into a pass. Execution paused for an explicit formatting
decision before changing the checker or executing another paid run.

Only **two** of the six new cases executed. Their observed completed usage was
**four model calls, three tool operations, 6,204 input tokens and 333 output
tokens**. Including the first failed attempt, the recovered completed totals
are **six model calls, four tool operations, 8,733 input tokens and 439 output
tokens**, approximately **$0.009377775** at the uncached chat meters, excluding
compute/build and unrelated work. These selected-item reads perform no query
embedding. Discovery/search, missing-item, absent-full-article and cancellation
were not executed in this rerun. No automatic retry followed the failure.

Actual probes under the amended agent workload identity independently verified
nondelegated MCP denial (**403**), embedding/screening/Responses denial
(**401**), management read/list-keys denial (**403**) and own/MCP/admin database
role denial (**28P01/28000**, zero SQL queries sent). No grants or workload
configuration changed. Current-revision research telemetry/cancellation and
final data/history preservation remain unverified. Callback and disposable
database ports were verified closed. Tasks 2.5, 4.1 and 4.2 remain unchecked;
publication and archival remain blocked.

The user subsequently confirmed that **only the final period on an individual
metadata claim is optional**. The independent checker accepts the exact
source/category template with or without that one period; all values, citations,
record coverage, comparison wording and complete-summary equality remain
strict. **13 checker regressions** pass, including rejection of invented values,
wrong citations, altered comparison claims, other formatting changes and shortened
summaries. The prior failed check remains retained. No runtime source, immutable
image, deployment, authority or budget limit changed.

A continuation permits **five new requests**, retrying comparison and executing
discovery/search, missing-item, absent-full-article and cancellation. The already
passed complete-summary/brief case is not repeated. Including all three prior
requests and recovered usage, the cumulative envelope is **eight requests,
26 chat calls, 44 tool operations, 1,319,453 chat input tokens and 20,919 chat
output tokens**, plus **120 embedding attempts / 983,040 embedding tokens**.
Its conservative current model-meter envelope is **$1.35**, excluding compute/
build and unrelated work; the same 30-minute wall limit and shared-pipeline
pacing apply. These are execution bounds, not actual consumption or a bill.

### Discovery prerequisite follow-up

The continuation's comparison passed with **three independently supported
claims, two exact citations**, same-user multi-call delegation and completed
readback parity. Constrained search then failed explicitly with
`research_missing_detail`: search returned metadata, but the next model plan
chose synthesis before requesting detail. The controller refused that plan
rather than answering from metadata or model recollection. Authenticated
aggregate telemetry recovered **two model calls, one tool operation, 2,435 input
tokens and 129 output tokens**, with both usages observed. No retry or successful
answer is inferred from this failure; the remaining three cases did not execute.

Two wire regressions first failed on the missing trusted discovery prerequisite.
Trusted instructions now distinguish search/recent metadata from detail evidence
and require a relevant discovered `get_news_item` plan before synthesis when
detail evidence is empty, within unchanged budgets. These authored wire tests
prove instruction delivery, not actual model compliance. **90 focused cases**
passed, followed by the complete PostgreSQL-enabled primary gate and all six
package builds: **1,218 tests / one intentional skip**, **131 typed files**,
**222 formatted files**, **13 strict OpenSpec items**, ten Terraform validations
and **71 mocked-provider cases**. Four near-limit/full-queue cases measured
**170.59 MiB** peak RSS. The owned database was stopped/removed and its port and
the callback port were verified closed.

Fresh retained-state inventory passed before the agent-only immutable build.
The new source is
`b28cd3c4dbf63c33cdcf4e8be8d06847bc36df556896170a89113343e294a362`;
its image is
`sha256:0db092840269971a790948b1a483a50de5c6d97c505953b044f395f925b8001f`.
Independent review of native plan
`2d712d888e63797df6d50f1c6338c133fb7325bd27b767970c0851e20c1de17a`
verified **zero additions, one in-place change, zero deletions**, changing only
the image and runtime source revision. Native apply succeeded. An initial
readiness mismatch remains retained; the unchanged full readiness/configuration/
identity/image and preservation checks subsequently passed at **22:30:50 UTC**.
The 19 resources, five other workloads, three models, grants and schedules remain
unchanged.

Preliminary Entra-authenticated telemetry inspection retained a checker failure:
it initially treated the SDK's `_APPRESOURCEPREVIEW_` resource marker as an
application metric. Follow-up queries separately verified its exact two-key
shape, fixed service, bound Application Insights application ID and zero metric
value; application-metric allowlists were not broadened. Research span names and
dimension keys, all eight application metric shapes and JSON console keys passed.
Boolean usage fields are checked as booleans, not case-sensitive strings.
Cancellation and current-candidate research telemetry remain pending.

A fresh full six-case run on the new candidate includes all earlier **five**
requests and recovered observed usage in its cumulative envelope: **11 requests,
34 chat calls, 55 tool operations, 1,587,673 chat input tokens and 25,335 chat
output tokens**. Including three conservatively reserved embedding attempts for
the prior successful search, the total embedding reservation is **147 attempts /
1,204,224 input tokens**. The conservative model-meter envelope is **$1.63**,
excluding build/compute/unrelated pipelines, with the same finite wall limit
and quota-aware pacing. All previous failed attempts remain failed, and live
acceptance/publication remain unchecked.

### Current candidate: state-aware planning decision remains open

The new full run again passed the exact complete-summary/brief conflict and
the two-item comparison, with independently supported claims/citations and
completed readback parity. Discovery then failed explicitly with
`research_unknown_item`. The controller executed one permitted read from the
first model plan, then encountered a detail argument whose ID was not known to
the request.
The controller rejected that argument before another MCP operation or a final
answer. Authenticated telemetry recovered **one model call, one tool operation,
1,108 input tokens and 147 output tokens**, with usage observed. This is a
different planning failure from the earlier premature-synthesis failure;
the trusted prerequisite text alone has not established reliable discovery.

The run stopped after **three** of six cases. Missing-item, absent-full-article
and cancellation cases were not executed. Across all **eight actual requests**,
recovered observed chat totals are **15 model calls, 11 tool operations, 22,293
input tokens and 1,239 output tokens**, approximately **$0.024524775** at uncached
chat meters. This excludes embedding, compute/build and unrelated work; embedding
transport attempts/consumption were not independently observed and are not zero.
No automatic paid retry followed the failure.

Current-candidate workload denials passed under the actual bound identity.
Entra-authenticated telemetry found **two successful and one failed research
execution**, the expected private trace/metric shapes and a JSON console record
with no unexpected fields. No cancellation was executed or inferred. Independent
MCP-identity SQL before/after found **2,097 records**, identical whole-news
metadata fingerprints and identical latest-ID/URL hashes. The three follow-up
runs began with the same selected-evidence fingerprint; no source content or
credentials were persisted. Callback and disposable database ports are closed.

Paid acceptance paused for a planning-design decision. The user chose
state-constrained planning rather than further prompt-only tuning; the approved
[design](../openspec/changes/archive/2026-10-28-agent-research/design.md#2-keep-the-model-selected-loop-application-owned-and-finite)
and task 2.6 track that follow-up. The failed candidate above is not relabeled.
Tasks 2.5, 2.6, 4.1 and 4.2 remained unchecked on that failed candidate. The
follow-up and verified delivery below do not alter its failed acceptance status.

### State-constrained planning follow-up

The local controller now snapshots request-owned evidence, completed calls and
remaining tool allowance before each planning turn. A frozen typed scope drives
the closed model schema and independent whole-plan validation. Detail choices
contain only eligible IDs known at turn start; unavailable tools and synthesis
states are omitted. Independent batches remain sequential, but discovery and
dependent detail reads require separate turns. Selected-item mode remains
application-bootstrapped, with no discovery substitution.

Synthesis is admitted with detail evidence, or stopping after healthy empty news
retrieval for controller-generated no-match without final generation. A source
listing alone cannot authorize absence. Every returned plan is checked against
its frozen scope and all existing call guards before any of its calls executes;
the original per-call checks remain active during dispatch. Invalid plans fail
explicitly without partial dispatch, ID substitution, repair, retries or widened
budgets. Schemas containing request-local IDs remain excluded from diagnostics.

New regressions first reproduced unrestricted detail/synthesis schemas,
dependent-ID admission and invalid-later-call partial dispatch. The complete
PostgreSQL-enabled primary gate passed **1,234 tests / one intentional skip**,
131 typed files, 222 formatted files, 13 strict OpenSpec items, ten Terraform
validations and **81 mocked-provider cases**, followed by all six package
builds. Four near-limit concurrent requests plus three full-eight-event-queue
cleanup cases passed at **170.43 MiB peak RSS**, below 400 MiB on the unchanged
profile. The owned disposable PostgreSQL instance was removed and its port
verified closed. Pylance found no syntax errors and all 14 generator plan call
sites were compatible. The 13 independent semantic-checker regressions passed
without relaxing full-summary or citation checks.

Local scripted responses establish wire shape and enforcement, not actual model
obedience or semantic quality.

Fresh inventory and current regional retail/quota checks passed before the
agent-only build. The follow-up's source is
`e338ee7ca7a08a55a586687e833dfcccaa82cd75ce5cba963ffb485dbd639651`;
the immutable image is
`sha256:a42d1d596a609075528e1752376715614ab90a9c035f54f30c1816bccde29e7c`.
The independently reviewed binary plan hash is
`3fb65395b982403e082ebb804865e7a531f87d95b4bf4447c7c0a17f232268ed`:
**zero additions, one in-place agent change, zero deletions**, changing only
the image and runtime source revision. Native owning apply succeeded.
Initial readback retained a latest-not-ready failure; unchanged full predicates
passed after activation at **2026-10-28 07:35:53 UTC**. The ready candidate,
public card/authorization guards, all 19 resources, five other workloads, three
models, grants, consent, identity and schedules passed independent preservation.

Actual bound-identity denials passed again: nondelegated MCP and management
read/listKeys were denied with 403; embeddings, screening and Responses with
401. Own, MCP-role and administrator database attempts were denied before any
SQL query. Independent MCP-identity SQL before live acceptance found **2,101
records**; the overnight increase is not treated as an agent write or a frozen
data-count failure. Counts and fingerprints only were retained.

A fresh six-request live envelope retains all eight prior requests and their
15 observed model calls, 11 tool operations, 22,293 input and 1,239 output tokens.
It reserves 24 additional model calls, 48 MCP operations and 144 possible
embedding transport attempts, plus six prior embedding attempts reserved but
not observed. The cumulative uncached-meter estimate is **$1.64**, not an
invoice or prepaid cap, and excludes compute/build and unrelated scheduled work.
Actual signed-in acceptance for this follow-up is recorded below.

### State-constrained actual acceptance

The first sign-in attempt timed out before any research request or model work.
After the user chose to reopen authentication, PKCE completed and the unchanged
six-case envelope passed against the verified source/image. The authentication
failure remains retained; no failed paid case was retried or waived.

| Actual case | Model calls | MCP operations | Independent outcome |
| --- | --- | --- | --- |
| Complete stored summary with brief preference | 2 | 1 | Entire summary and exact stored citation matched |
| Two selected items compared by metadata | 2 | 2 | Three supported claims, two exact corresponding citations |
| Constrained semantic search, then detail and synthesis | 4 | 2 | Entire discovered summary and exact stored citation matched |
| Missing selected item | 0 | 1 | Honest no-match; no claims, citations or generation |
| Unavailable full article | 2 | 1 | Exact honest limitation; no invented claim or citation |
| Cancellation during planning | 1 admitted, usage unobserved | 1 | Cancelled readback, no artifact or completed state |

All five completed requests preserved the originating user, emitted safe
progress before validated artifacts and matched completed readback exactly.
Discovery used separate search/detail turns and legal final synthesis with the
actual pinned strict-schema connector. This verifies the focused case, not
reliable behavior on all questions or a phase-wide quality score. Cancellation
acknowledgment/awaited cleanup took **0.123 seconds**; its consumption remains
unknown, not zero.

The five completed requests observed **10 model calls, seven MCP operations,
12,593 input tokens and 638 output tokens**, approximately **$0.01354732** at
uncached chat meters. Across all 14 research requests, 25 metered model calls
account for **34,886 input / 1,877 output tokens**, approximately **$0.03807210**.
One additional planning call was admitted for cancellation with no usage
observed. These estimates exclude query embeddings, cancellation consumption,
compute/build and unrelated scheduled work; they are not invoices.

Entra-authenticated telemetry independently found **five successful research
executions, one cancellation and zero research failures** on this candidate.
Every trace name/dimension, all eight application metric shapes, the separately
validated SDK resource marker and four JSON console records passed the unchanged
privacy allowlists. No question, preference, plan/schema IDs, article text, URL,
answer or credential values were returned by the verification queries.
The zero-generation no-match record does not establish metered usage; the
separate cancellation record explicitly retains incomplete coverage.

Independent MCP-identity SQL before/after found **2,101 records** with identical
whole-news metadata and latest-ID/URL fingerprints. The selected-record
fingerprint also matched after all six cases. Time-correlated execution history
showed successful ingestion/enrichment at the preserved **07:30 and 08:00 UTC**
schedule boundaries, with no new migration or phase-acceptance execution.
No data was restored, deleted or modified by acceptance.

One final ARM read command failed; an isolated read then succeeded, followed by
the unchanged complete verifier at **2026-10-28 08:06:24 UTC**. The failed read
receipt remains retained without guessing its cause. Final source/image,
readiness, public guards, all resources, other workloads, grants/consents,
models/capacities and schedules matched the reviewed boundaries. Actual
bound-identity denials above remain verified. The owned database and callback
ports are closed. Runtime acceptance and implementation publication are complete; the separate
evidence/status publication is recorded below. Archival requires review.

### Verified research implementation publication

The verified implementation was committed and pushed as
[`563aeebc6ca70a80f4516c760498323feaa9d169`](https://github.com/ikhemissi/newsloom/commit/563aeebc6ca70a80f4516c760498323feaa9d169).
Its primary [exact-SHA CI](https://github.com/ikhemissi/newsloom/actions/runs/40654767524)
passed. This Git publication does not replace the independently retained
runtime source, immutable image and exact reviewed plan hashes above.
No runtime source changed after actual acceptance.

Unrelated OpenSpec customization changes and all private environment/evidence
were excluded. Tasks 2.5, 2.6, 4.1, 4.2 and 5.1 are verified. The separate
measured evidence/status receipt and its CI are recorded below.

### Verified research delivery

The separate measured evidence/status publication is
[`4d017e1f742f661fdd2deafc2ddf75052b1fcb42`](https://github.com/ikhemissi/newsloom/commit/4d017e1f742f661fdd2deafc2ddf75052b1fcb42),
with passing primary
[exact-head CI](https://github.com/ikhemissi/newsloom/actions/runs/40655231221).
Only after that result was task 5.2 checked. All **17 research tasks** are
verified; **Step 2.2 is delivered**. Runtime source/image/plan provenance remains
the independently verified binding above, not the later documentation heads.

The completed change was reviewed and archived as recorded below.
Step 2.3's frozen phase-wide quality evaluations, DeepEval/Foundry
integration, cost-governance refinement, deferred web/toolbox, persistent
memory/Work IQ and the browser UI remain pending. Passing focused acceptance
does not replace that evaluation baseline or authorize those additions.

### Verified research archival

The 2026-10-28 prerequisite review verified all 17 tasks, the measured local/Azure
receipts above and passing implementation, evidence/status and final-head
[completion CI](https://github.com/ikhemissi/newsloom/actions/runs/40655780806).
After the user selected synchronization, all ten research requirements were
published to the [main research contract](../openspec/specs/news-research/spec.md).
The A2A discovery requirement was updated while preserving its original purpose
and six other requirements. Canonical delta/main comparisons and strict main-spec
validation passed before moving the change to its
[dated archive](../openspec/changes/archive/2026-10-28-agent-research/proposal.md).
Historical failures, observed costs and source/image/plan receipts remain intact.
Archival makes no runtime, resource, permission or model change and does not
repeat paid acceptance. Step 2.3 remains a separate delivery.

## Verified local package and protocol set

The owning [agent package](../services/agent/pyproject.toml) pins:

| Component | Version |
| --- | --- |
| Python | 3.15.1; supported interval `>=3.15,<3.16` |
| Agent Framework core | 1.23.0 |
| Agent Framework OpenAI connector | 1.17.0 |
| OpenAI SDK | 3.39.0 |
| Agent Framework A2A adapter | 1.0.0b261022 |
| Official A2A SDK with `http-server` extra | 1.2.3 |
| Azure Identity | 1.26.0 |
| MCP client | 2.3.0 |
| MCP client's HTTPX2 transport | 2.16.0 |
| Starlette / Uvicorn | 1.9.0 / 0.54.0 |

The adapter's explicit prerelease pin does not enable prereleases globally.
The minimal graph adds 15 packages, including `newsloom-agent`; all 89 prior
lockfile package versions and sources remain unchanged. Serving adds only
`types-protobuf` to development dependencies for strict typing of the pinned
SDK's protobuf parsing API (105 packages at that stage). The post-delegation
model stage adds the official optional `agent-framework-openai` connector,
OpenAI SDK, `jiter` and `sniffio`: **109 locked packages**, retaining all prior
versions. Azure Monitor/OpenTelemetry were already in the graph and are now
direct agent dependencies. Core's optional `telemetry` extra supports the shared
span-rebuilding helper without adding telemetry to its base installation.

The verified wire interface is **A2A 1.0 JSON-RPC over HTTP**, discovered at
`/.well-known/agent-card.json`. SDK 1.2.3 uses protobuf types, not the older
Pydantic message constructors. The compatibility probe uses
`create_agent_card_routes`, `create_jsonrpc_routes`, `DefaultRequestHandler`
and `A2AExecutor`; the client uses `A2ACardResolver` and `ClientFactory`.
The actual application uses the same official routes/executor with its own
bounded `RequestHandler` and producer-side `EventQueue` implementation.

[Compatibility tests](../tests/test_agent_compatibility.py) bind an OS-assigned
loopback port, discover the real HTTP card, invoke through the official client,
retrieve the completed task and check the exact response. Both executor modes
and both client modes are tested. The non-streaming executor returns its message
through task status/history rather than an artifact. Streamed chunks share an
artifact ID with correct append behavior and a completed terminal status. All sockets, servers
and clients are closed after the tests. This deterministic test-only provider
does not call Azure, MCP, Entra or a real model and is not a deployed agent.

## Local commands

Install through the [workspace setup](../README.md#local-development), then:

```bash
uv run --isolated --locked --no-dev --package newsloom-agent newsloom-agent check-runtime
uv run --locked pytest tests/test_agent_compatibility.py tests/test_workspace.py tests/test_mcp_auth.py tests/test_mcp_http.py
uv run --locked mypy services/agent tests/test_agent_compatibility.py tests/test_workspace.py
uv build --package newsloom-agent
```

`check-runtime` imports the actual authenticated application, official A2A client/server, async
Azure Identity and MCP client without reading environment configuration or
making a service request. Its output is a content-free module count, not live
acceptance. In the model-stage checkout, `serve` starts the protected streaming
service on port 8000; it requires the original trusted configuration plus the
[model-stage inputs](#runtime-and-owning-app-inputs).
Missing model/telemetry configuration fails startup rather than silently
falling back to the earlier non-generative runtime. Package-only startup is part of
the [primary check](../scripts/check.sh).

## Deployment boundary

Do not deploy the compatibility probe or expose an unauthenticated placeholder.
The SDK itself is not the agent authorization/privacy boundary: its default
executor can log and return exception text. The delegated runtime must protect
all enabled routes and sanitize failures before it is ready for deployment.

The existing ACA environment and Foundry account remain authoritative. No
Foundry project is selected in the VS Code extension; that does not authorize
creating one or replacing retained azd state. Owning previews, consent and cost
approval are required before cloud mutations. The actual signed-in OBO gate
must pass before model-backed expansion. Local SDK streaming is not that gate
and does not establish real Foundry streaming or user preservation.

## Separate audiences and private callers

The [shared verifier](../packages/newsloom-core/src/newsloom_core/auth.py)
owns only trusted-key refresh, signature/issuer/audience/lifetime validation and
typed claims. Its optional `auth` dependency is requested by MCP and the agent,
not required by base core. Existing MCP claims and the
[MCP adapter](../services/mcp/src/newsloom_mcp/auth.py) retain their previous
scope behavior: `news.read` is the only accepted delegated MCP permission.
`news.agent` is not an alternate MCP permission.

The agent's full delegated scope is `api://<agent-api-client-id>/news.agent`.
The PKCE request, static card, token verifier, registration inventory and consent
all use that exact scope, with no legacy alias. The Terraform output key
`AGENT_INVOKE_SCOPE` is unchanged; its value uses `/news.agent`. This rename
preceded agent registration/deployment and made no Azure changes.

The [agent policy](../services/agent/src/newsloom_agent/auth.py) requires its own
audience and `news.agent`, plus verified tenant, object, subject and authorized
client claims. App-identity markers and ID-token nonce claims are rejected.
Missing/invalid authorization returns 401, insufficient delegated scope returns
403, and trusted-key availability or authentication deadline failures return a
safe 503 category. No upstream error body is returned.

The authentication wrapper guards every HTTP method/path by default; only GET
of the static agent card and `/health/live` bypasses it. WebSockets are refused.
Authorization-only tests use a downstream operation spy. The serving tests
also exercise real HTTP, official A2A clients and the actual delegated
adapters against local identity/MCP transports. No deployed tool/model
invocation is claimed.

Verified caller assertions and identity values are kept only in private,
immutable request objects with representations suppressed. Authorization
carries the original 120-second deadline capped by incoming token expiry.
Future request stages must consume it rather than start a new budget. Compare
users privately by `(tenant, object_id)`; subjects can differ across audiences.
Never put the caller, assertion, claims or a token fingerprint into diagnostics.

The locally signed
[authorization tests](../tests/test_agent_auth.py) cover two-user concurrency,
cross-audience/scope denial, missing/wrong claims, signatures, algorithms,
caller-directed key URLs, bounded key refresh, key-response failures, token size,
expiry, duplicate headers, public-route exceptions and content canaries.
The unchanged MCP authentication/HTTP/privacy regressions pass. These are local
tests, not Entra consent, actual federation, OBO or live user-preservation proof.

Focused checks for this extraction:

```bash
uv run --locked pytest tests/test_agent_auth.py tests/test_agent_compatibility.py tests/test_mcp_auth.py tests/test_mcp_http.py tests/test_mcp_privacy.py tests/test_mcp_verification.py tests/test_workspace.py
uv run --locked mypy
uv run --locked ruff check .
uv run --locked ruff format --check .
```

The observed extraction run passed 111 tests; four database-dependent MCP
verification tests were skipped because no explicit PostgreSQL helper was
started. All 102 typed source files passed. Isolated no-dev core without auth
extras, agent, MCP and ingestion startup passed. This is not the later complete
local gate, which must include the database tests.

## Opt-in owning agent identity layer

The [identity layer](../infra/agent-identity/main.tf) has its own retained
`newsloom/<environment>-agent-identity.tfstate` key. Its providers remain
AzureRM **5.10.0** and AzureAD **3.10.0**, without shared-provider upgrades.
The [azd layer](../azure.yaml) depends on the existing application and MCP
identity outputs, not the MCP application/build hook. The shared four-workload
identity set is unchanged.

The layer owns one new user-assigned identity, a single-tenant v2 middle-tier
API exposing only `news.agent`, and a separate public acceptance client.
The client's only callback is **`http://127.0.0.1:8400/callback`**; the explicit
browser PKCE helper is described below. The API
requests only the existing MCP delegated `news.read` scope, not an application
permission. The API's sole federation binds the configured tenant's exact
v2 issuer, the new identity's principal/object ID (not its client ID) and
`api://AzureADTokenExchange`. It is not GitHub OIDC federation.

Azure grants are limited to `AcrPull` on the existing registry, `Monitoring
Metrics Publisher` on the existing Application Insights component, and a custom
chat-completions-only data action on the existing Foundry account. The layer
creates no database role, embedding/screening authority, management permission,
model, app, job or shared resource.

`AGENT_ENABLED` and **separate** `AGENT_CONSENT_ENABLED` both default to false.
The latter controls two exact tenant-wide **delegated** grants: agent API to
MCP `news.read`, and acceptance client to agent API `news.agent`. They are
not application grants, do not bypass signed-in-user verification, and require
explicit review/consent approval. Configuration alone is not OBO evidence.
Do not disable either setting after delivery as a casual rollback: identity
destruction is prevented, and existing consent cannot be silently removed by
the preparer. App ingress/revision rollback belongs to its owning app task.

### Read-only inventory and permissions

The [preparer](../services/platform/src/newsloom_platform/agent_identity.py)
is also the layer's preprovision hook:

```bash
uv run --locked newsloom-platform prepare-agent-identity
```

With the default disabled flag it makes no Azure calls and fills private azd
inputs with disabled/empty values. When enabled, it only inventories directory
objects and writes ignored retained-environment inputs; it never creates an
app, grants consent or changes Azure resources.

The existing MCP API/public client must already be explicitly configured.
They are read and validated, not updated. Existing agent registrations may be
adopted only by explicit `AGENT_API_CLIENT_ID` / `AGENT_PUBLIC_CLIENT_ID`.
Display-name discovery detects collisions; it never selects an app. Adoption
requires exact contracts, no credentials/app roles or extra redirect surfaces,
same-tenant enabled principals, the signed-in operator as the sole app owner,
exact federation and exact existing consent. Different/shared ownership,
extra scopes/federations or user-specific/broader grants stop for review
instead of being normalized or overwritten. An existing managed identity must
already be owned by this retained layer; an untracked collision needs a reviewed
state-adoption decision, not recreation or automatic takeover.

Before any enabled preview/apply, privately verify:

- The signed-in operator can read these exact apps, principals, owners,
  federation and consent, create/own the new registrations, and manage the
  new managed identity in the existing resource group.
- The provider's directory and delegated-consent permissions are actually
  available. Its [consent resource documentation](https://registry.terraform.io/providers/hashicorp/azuread/3.10.0/docs/resources/service_principal_delegated_permission_grant)
  documents elevated directory authority; do not grant broad roles to work
  around a missing permission. Separate administrator review is required.
- Azure RBAC permits the exact custom role/three narrow assignments. The
  agent workload itself receives none of the operator's management authority.
- Exact retained resource IDs, current production baselines, cost and
  native target-layer previews have been reviewed under task 3.1.

After approval, use only owning target-layer commands through retained azd;
never run `terraform apply` or an unqualified all-layer update. In particular,
shared-source changes can otherwise trigger an unintended MCP rebuild.
The enabled identity preview and approved identity-only provisioning are recorded
below. The app and actual Azure OBO exchange remain unverified.

### Initial read-only cloud preflight

After the complete local gate, exact registration inventory confirmed the
existing MCP contract and no existing agent API/acceptance registrations.
Private baseline files retain the 17 existing resources, five immutable
app/job configurations, two schedules and three unchanged configured model
deployments. No cloud resource, grant, image or environment setting was changed.
This is a baseline for a later comparison, not completed preservation acceptance.

The retained chat deployment is `gpt-5.4-mini`, version `2026-03-17`,
`DataZoneStandard`, capacity 10. Its regional quota inventory showed 110 of
1000 allocation units used across the subscription/region; that is not a
measurement of live throughput or unused request-rate capacity. No new model
allocation or inference was requested.

The operator has Azure `Owner`, but the initially observed active directory roles
did not establish tenant-wide delegated-consent authority. Tenant policy permits ordinary
app registration; that does **not** imply consent-administrator authority.
An authorized Entra administrator must review the two exact delegated grants
before the consent gate is approved. Do not add broad roles or work around it
with credentials, app-only access or a modified MCP policy.
The pinned AzureAD 3.10.0
[grant resource documentation](https://registry.terraform.io/providers/hashicorp/azuread/3.10.0/docs/resources/service_principal_delegated_permission_grant)
specifies `Global Administrator` for its user-authenticated execution path.
Microsoft's [portal consent documentation](https://learn.microsoft.com/en-us/entra/identity/enterprise-apps/grant-admin-consent)
allows narrower administrator roles for these custom delegated APIs, but that
does not verify the Terraform path with such a role. Use an existing authorized
administrator under the organization's process; do not assign a broad role as
a workaround. A separate portal-consent/adoption execution path would need
explicit review before replacing the approved azd-managed grant step.

The public [Azure retail price API](https://prices.azure.com/api/retail/prices)
returned France Central consumption rates. For one 0.25-vCPU/0.5-GiB replica
over 730 hours, the marginal compute estimate is **USD 5.91/month if idle**
or **USD 19.71/month continuously active**, before shared free grants, taxes,
telemetry, egress and ACR build charges. Requests are USD 0.40/million before
applicable free grants. This non-generative stage makes no model calls; later
token usage needs its own estimate before the model stage.

Task 3.1 remains unchecked: administrator review, native enabled owning
previews, remaining data/API/capacity checks and explicit mutation approval
are still required. No build, consent or provisioning is authorized by these
read-only observations.

### Enabled identity-only preview

After the operator activated their existing PIM role, a fresh read-only Graph
membership check verified active `Global Administrator` under the same operator
and retained environment. No directory role was assigned by this workflow.
Exact MCP inventory still matched, and neither new agent registration nor a
colliding agent managed identity existed.

Only ignored local azd inputs were prepared with `AGENT_ENABLED=true` and
`AGENT_CONSENT_ENABLED=true`. These flags enabled the **preview**, not consent
or provisioning. The native `azd provision agent-identity --preview --no-prompt`
succeeded: **13 additions, zero changes, zero deletions**.

Independent inspection of the generated native plan established:

- Two separate single-tenant apps and their service principals, owned solely by
  the unchanged operator, with the exact IPv4 PKCE callback.
- Only `news.agent` on the new API and delegated `news.read` on the existing MCP;
  two exact tenant-wide delegated grants, not application permissions.
- The separate managed identity, exact same-tenant issuer/exchange audience and
  principal-bound federation.
- Only registry pull, authenticated telemetry and chat-completions authority at
  their owning retained scopes; no database or MCP application authority.

The 13 additions comprise two app registrations, two service principals, one
API identifier URI, one federation, two delegated grants, one managed identity,
one custom chat role and three narrow RBAC assignments. No app, image build,
model allocation or existing MCP/shared-resource modification is in this plan.
Private evidence retains the plan fingerprint and exact review.

An independent post-preview readback still found **17 resources**, no new agent
managed identity and exact matches for all five retained app/job configurations.
No other service's build hook ran. The owning preview itself did not run the
complete global check hook; the full primary gate is run explicitly rather than
inferred from preview success. Owned local preview helpers were stopped.

Identity/consent apply requires explicit approval of this exact scope. The app
image build, app-only preview/provisioning and actual signed-in OBO remain later
gates; task 3.1 is not complete merely because its identity preview passed.

### Approved identity-only provisioning and independent readback

The operator explicitly approved the reviewed identity provisioning and its two
tenant-wide delegated consents. Native `azd provision agent-identity --no-prompt`
completed with **13 additions, zero changes, zero deletions**. No app, image build
or model call was included.

Independent directory/ARM reads verified the two separate registrations and
principals, exact callback and `news.agent` contract, the principal-bound
federation, both exact delegated consents, the managed identity and exactly three
narrow role assignments. The custom role contains only chat-completions data
access. The original four-workload identity map and MCP/pipeline inputs are
unchanged. Post-apply reads exactly matched all five retained workload
configurations, both schedules and all three existing model deployments.
The resource group now has 18 resources, adding only the new managed identity.

The first independent readback exposed a local verifier defect: Azure's identity
list returned the same ARM path with `resourcegroups` casing, while Terraform's
output used `resourceGroups`. All actual federation fields matched. A failing
local reproduction was added before fixing the resource-path comparison to use
case-insensitive ARM semantics; foreign/malformed paths still fail, and tenant,
principal, issuer, audience and permission checks are unchanged. The focused
identity/MCP/operator regression selection passed **186 tests**, and strict
typing for 115 files plus focused lint/format passed.

After retaining the independently verified registration/adoption inputs, a fresh
native identity-only preview passed with **no pending managed-resource changes**.
Private receipts retain exact plan/readback fingerprints and the initial failed
readback. This is verified identity setup, **not** live user-preserving OBO or
agent acceptance. Task 3.1 still requires the remaining preflight and separately
approved immutable build/app-only deployment; task 3.2 still blocks model work.

### Local identity evidence

[Inventory tests](../tests/test_agent_identity.py) exercise actual preparation
logic with read-only local Azure CLI responses, including new versus explicitly
adopted registrations, forbidden identity reuse, wrong/foreign IDs, sole-owner
checks, credential/redirect/scope/federation/consent mismatches and content-free
receipts. The existing MCP inventory tests are unchanged.

The [15 mocked-provider cases](../infra/agent-identity/tests/identity.tftest.hcl)
pass, covering disabled/no-resource behavior, separate consent opt-in, exact
federation and delegated scopes, narrow grants, invalid IDs/callbacks/adoption
and foreign tenant/resource/MCP permission refusals. Terraform validation and
recursive formatting pass. The combined runtime, identity and platform-control
selection passed **419 tests**, with four explicit database-dependent skips;
all **109 typed files** and workspace lint/format passed. See the
[subsequent complete gate](#complete-offline-pre-cloud-gate) for database-backed
task 2.3 evidence; these are not Azure permission or live OBO proofs.

```bash
terraform -chdir=infra/agent-identity init -backend=false -input=false -lockfile=readonly
terraform -chdir=infra/agent-identity validate
terraform -chdir=infra/agent-identity test
uv run --locked pytest tests/test_agent_identity.py tests/test_mcp_identity.py tests/test_platform_contracts.py tests/test_platform_control.py
```

## Request-local delegation adapter

The [delegated adapter](../services/agent/src/newsloom_agent/delegation.py)
accepts trusted tenant/API/resource configuration, the shared agent workload
credential and a trusted-key client. It accepts no request-selected authority,
resource, endpoint, tool name or alternative credential.

For each authorized request it:

1. Asynchronously obtains an MI assertion for
   `api://AzureADTokenExchange/.default`.
2. Requires enough assertion lifetime for the entire remaining request plus a
   30-second margin, then creates a fresh async `OnBehalfOfCredential`.
   Its synchronous callback only checks time and returns the prefetched string;
   it performs no network I/O.
3. Requests only `api://<existing-mcp-api-client-id>/.default` from the fixed
   public-cloud tenant authority. The owning consent must contain only
   `news.read`; actual consent and federation are still unverified.
4. Signature-verifies the downstream token with trusted tenant keys, requiring
   the MCP audience, exactly `news.read`, the middle-tier authorized client and
   matching private tenant/object identity. Subjects need not match.
5. Creates an owned HTTPX2 client and native MCP session, initializes the
   protocol and calls exactly `get_recent_news(limit=1)`. It returns typed news
   and a safe user-preservation comparison, never either token.

The shared MI credential may be reused; user assertions, OBO credentials,
downstream tokens, headers, MCP clients and results are not shared across
requests. All stages consume the original deadline and incoming authorization
lifetime, additionally capped by the exchanged token's signed/provider expiry.
OBO and MCP clients close on success, failure, timeout and cancellation.

The current MCP SDK requires **HTTPX2**, not the separate HTTPX used for JWKS and
A2A. That already-locked dependency is now explicit in the agent manifest.
Its default client also follows some same-origin redirects regardless of the
HTTP client's setting. The adapter therefore rejects all redirects, checks the
exact configured HTTPS `/mcp` URL and authorization channel before each send,
disables environment proxy/auth configuration and bounds response bytes to
128 KiB, including JSON and SSE. It does not start an OAuth-interaction fallback.
The existing MCP endpoint is stateless; no persistent client session is retained
or network termination request sent after its authorization budget ends.

A small `ClientSession` override validates the fixed
[recent-news DTO](../services/agent/src/newsloom_agent/models.py), not
server-selected JSON Schemas or remote references. It neither lists/selects
tools dynamically nor fetches news URLs. Extra/malformed results or more than
one item fail; an empty item tuple is explicit absence, not an error fallback.
Generation, direct PostgreSQL access and operator/app-only MCP access do not
exist in this adapter.

### Local adapter evidence

[The SDK transport tests](../tests/test_agent_delegation.py) run the real async
Azure Identity OBO credential against a local transport, inspecting its actual
OAuth request/callback and closure. The real MCP client exchanges protocol
frames with the local MCP server over in-memory HTTP transports. This is not
an Azure federation test or a claim of live OBO.

The 54 adapter tests passed with exact safe categories for invalid-grant and
interaction-required consent, malformed exchange responses, wrong
signature-bound identities/resources/permissions, MCP denial and malformed
results, two-user concurrency, no reuse after prior success, response-byte
boundaries, empty versus failed news, rejected redirects, deadline/expiry and
cancellation cleanup. Some malformed identity responses are surfaced by the
actual SDK as `ClientAuthenticationError`, hence the safe `exchange_denied`
category rather than a raw response diagnostic.

The combined agent/MCP/workspace regression selection passed 166 tests with
the same four explicitly database-dependent skips. Strict typing passed for
104 source files, and workspace lint/format checks passed. Regression tests
also established explicit refusal of non-string SDK access tokens and a finite
request budget even for a signed, extremely distant expiry; neither reaches an
unhandled type/overflow failure.

Success emits only item count and a user-preservation boolean. Dependency logs
go through the existing content-free handler; canaries in news, credentials and
provider errors are absent from emitted diagnostics. This is not the later
framework/model/authenticated-telemetry acceptance gate.

```bash
uv run --locked pytest tests/test_agent_delegation.py
uv run --isolated --locked --no-dev --package newsloom-agent newsloom-agent check-runtime
uv build --package newsloom-agent
```

## Non-generative authenticated A2A application

The [application](../services/agent/src/newsloom_agent/app.py) is an injectable
ASGI factory, not an unauthenticated placeholder or an operator credential
shortcut. The managed-identity-only runtime and owning image are described
below. The only supported input is one `text/plain` part
containing `recent-news`, optionally surrounded by whitespace. Other requests,
files, URL/data parts, references, required extensions, push configurations,
detached execution and alternative output formats fail before OBO admission.
Request metadata cannot supply executor/provider keyword arguments.

The static public card describes exactly one stored-news read and advertises
**no streaming, generation or research**. It documents the separate Entra
authorization-code/PKCE scope and the A2A 1.0 JSON-RPC HTTPS interface. Only
loopback test servers may use HTTP. Invocation requires `application/json`
and `A2A-Version: 1.0`; legacy 0.3 is not enabled. Host validation and a
default-deny browser-origin policy apply. No debug/Inspector bypass is exposed;
the Foundry Inspector's Responses-API workflow is not an implemented transport.

An admitted request invokes the real `A2AExecutor` with a fresh request-local
Agent Framework provider, session and delegated read. Successful nonempty
output is structured JSON text with `outcome: news`, the actual MCP DTO and
`user_preserved: true`; zero items instead yields `outcome: empty`. Denied or
unavailable dependencies yield a failed task with an application-controlled
category, never a completed empty/model-only answer. The event boundary
replaces the executor's raw exception message before it reaches task state.
Runtime logs must use the existing content-free logging handler.

### Enabled task operations and finite profile

[Task handling](../services/agent/src/newsloom_agent/serving.py) keeps only
transient caller-owned records, without credentials or SDK call contexts.
The context builder passes only a fixed protocol-version header to the SDK;
incoming bearer/identity headers never enter its state. Credential-bearing
request context variables reset on exit; expiry timers have an empty context.

| Limit | Enforced local boundary |
| --- | --- |
| Request body | 65,536 bytes, counted while receiving, including chunked input |
| Input text | 16,384 UTF-8 bytes |
| Active private requests | Four, including auth/body/task operations; excess returns 429 |
| Retained tasks | 64; no active-task eviction to admit more work |
| Task retention | At most 300 seconds from admission; idle timers remove state |
| End-to-end duration | 120 seconds from ingress, capped by verified caller expiry |
| Generated output | None at this stage; the later proposed limit is 512 tokens |

`SendMessage` waits for the result and returns a server-generated task/context.
`GetTask` reads owned state with history length 0-10.
`ListTasks` provides owned metadata-only pages (default 50, maximum 64), with
owned cursor/context checks. It rejects unsupported history/artifact/status
filter options instead of silently ignoring them. This allows a non-streaming
client to find and cancel its in-flight request. `CancelTask` cancels the actual
producer and waits for cleanup under the original deadline before returning
canceled state. It cannot cancel completed tasks.

An owned context may be referenced for another independent one-read request;
it does not restore model history. Task continuation is explicitly unsupported.
Foreign/unknown task/context/cursor references are unavailable, never authority.
Streaming/subscription, extended cards and push operations are explicitly
unsupported and do not start providers. Restart/expiry returns not-found, with
no replay. Public liveness/discovery do not consume private-request capacity.

Body receipt, authentication, execution and cancellation share the original
budget. HTTP disconnect cancels and awaits the request producer, including
real OBO/MCP resource cleanup. Canceled, timed-out and interrupted work cannot
become completed output. Shutdown cancels producers and removes transient state.

### Local serving evidence

[Serving tests](../tests/test_agent_serving.py) verify real loopback HTTP
discovery/invocation and official-client task read/list/cancel, including actual
Azure Identity/MCP SDK transport cleanup during exchange and tool I/O. They
also cover two interleaved users, foreign/unknown references, pagination,
unsupported methods/inputs/configurations, exact byte/text/concurrency/task/TTL
and deadline boundaries, idle expiry without retained authorization, restart,
real socket disconnect, caller expiry, slow bodies, safe failures and content
canaries. These transports are local, not live Entra or Azure acceptance.

The combined agent/MCP/workspace selection passed **237 tests**, with four
explicit PostgreSQL-dependent skips. Strict typing passed for **107 files**;
workspace Ruff lint/format passed. See the
[subsequent complete gate](#complete-offline-pre-cloud-gate) for the full
database-backed checks. Authenticated automatic-telemetry/model privacy
acceptance remains a later task.

```bash
uv run --locked pytest tests/test_agent_serving.py tests/test_agent_auth.py tests/test_agent_delegation.py tests/test_agent_compatibility.py tests/test_mcp_auth.py tests/test_mcp_http.py tests/test_mcp_privacy.py tests/test_mcp_verification.py tests/test_workspace.py
uv run --locked mypy
uv run --locked ruff check .
uv run --locked ruff format --check .
```

## Owning app, immutable image and operator commands

The [app layer](../infra/agent/main.tf) owns only the new agent app in
`newsloom/<environment>-agent.tfstate`. Its azd dependencies are the existing
application, MCP identity and new agent identity layers, not ingestion,
enrichment, migrations or MCP app hooks. It defaults to disabled. The enabled
profile is one always-on Consumption replica, maximum one, 0.25 CPU/0.5 GiB,
one unprivileged process, HTTPS ingress and explicit startup/liveness/readiness
probes. Readiness means process readiness, **not** successful federation or OBO.
Browser origins default to none; the native acceptance client needs no CORS grant.

The [Dockerfile](../services/agent/Dockerfile) installs only the locked agent
package and runtime dependencies, with no development dependencies, database
client, credential fallback or Inspector endpoint. The
[runtime](../services/agent/src/newsloom_agent/runtime.py) uses only the
explicit user-assigned `ManagedIdentityCredential`. It requires:

| Trusted input | Purpose |
| --- | --- |
| `AGENT_TENANT_ID` | Fixed single-tenant authority |
| `AGENT_API_CLIENT_ID` | Separate agent audience/middle tier |
| `AZURE_CLIENT_ID` | Agent workload identity only |
| `MCP_API_CLIENT_ID`, `MCP_RESOURCE_URL` | Existing audience and canonical HTTPS `/mcp` |
| `AGENT_RESOURCE_URL` | Canonical HTTPS `/a2a`, derived from the retained ACA environment |
| `AGENT_RUNTIME_REVISION` | Immutable image input/source hash for operator readback |

Runtime configuration, registration IDs and layer outputs stay in ignored azd
configuration. The runtime accepts only explicit HTTPS origins if configured;
the current azd layer deliberately uses its empty default.
No database, model endpoint or user credential is injected into this temporary
non-generative app.

The [operator helper](../services/platform/src/newsloom_platform/agent_control.py)
separates **build**, **preview preparation** and **read-only verification**:

```bash
# Only after task 3.1 inventory and approval of the build/cloud changes:
uv run --locked newsloom-platform build-agent
uv run --locked newsloom-platform prepare-agent-layer
azd provision agent --preview
# Review that exact app-only preview and obtain approval before applying:
azd provision agent
uv run --locked newsloom-platform verify-agent
```

`build-agent` is an explicit Azure mutation: it builds only `newsloom-agent`,
then retains its immutable digest and matching `AGENT_IMAGE_REVISION`.
The `agent` preprovision hook **does not build**: it refuses an absent/mutable
image, missing identity output or source-hash mismatch. Thus a native
`azd provision agent --preview` cannot trigger an ACR build or another service's
build hook. For identity changes use only
`azd provision agent-identity --preview`, then its approved owning apply.
Never use an unqualified all-layer update, `azd up` or direct Terraform apply
for this slice. Required identity creation/consent precedes the app, so review
the first deployment in stages; do not invent a digest to obtain an app preview.

`verify-agent` independently reads the exact ARM app and checks the sole assigned
identity and its client/principal, immutable image, source revision, complete
trusted environment, ingress/FQDN, ready revision, registry authentication,
resources, scale and all three probes. Its receipt contains only comparisons
and the source hash. It is not a signed-in invocation, permission exercise or
live OBO receipt.

### Failure, disable and compatible rollback

A failed build or source/configuration check stops before app provisioning;
do not rebuild MCP, widen consent or substitute an operator token. Keep the
previous agent digest, matching source hash and verified runtime source revision
privately before an update.

For an approved emergency disable, remove **only the owning app**:

```bash
azd env set AGENT_RESEARCH_ENABLED false
azd env set AGENT_ENABLED false
azd provision agent --preview
# Proceed only if this removes the agent app and nothing else:
azd provision agent
```

Do **not** provision `agent-identity` or another layer with that disabled flag.
The app-only operation retains registrations, consent, its managed identity,
shared resources, models, schedules and stored data. Do not run `azd down`.

To restore a previously verified image, first safely preserve local work and
use its matching verified runtime source with the **same retained azd
environment/backend**, not newly initialized infrastructure. Set
`AGENT_ENABLED=true`, `AGENT_IMAGE` to that previous immutable agent digest and
`AGENT_IMAGE_REVISION` to its matching input hash. Run `prepare-agent-layer`,
review `azd provision agent --preview`, apply only that layer after approval,
then rerun `verify-agent` and signed-in acceptance. A mismatched checkout/hash
is intentionally refused; do not bypass that check. These commands are
documented recovery paths, not a claim of a live rollback drill.

## Explicit signed-in acceptance client

The [client](../services/agent/src/newsloom_agent/client.py) is an operator
acceptance tool, not a production UI. After the approved deployment and consent,
run it with the ignored retained environment's values:

```bash
uv run --env-file ".azure/<retained-environment>/.env" --locked --no-dev \
  --package newsloom-agent newsloom-agent verify-delegation
```

Replace the quoted environment placeholder with the existing environment name.
In addition to the runtime's tenant/API/MCP/resource inputs, the client requires
`AGENT_PUBLIC_CLIENT_ID` for the separate PKCE registration; it does not use
the workload managed identity or an operator access token.

The command explicitly opens the browser for account selection using S256 PKCE
and unpredictable state. Only IPv4 loopback port 8400 and the exact callback
path/host are accepted. Port conflict, invalid callback/state, browser failure
and timeout fail explicitly and close the listener. Sign-in is bounded to
180 seconds; token responses to 32 KiB. No secret, offline scope, refresh-token
acceptance, persistent token cache or identity-dump endpoint is used.

The client verifies the access-token signature/audience and public-client claim,
discovers the static card without a bearer, validates its endpoint/protocol/
security contract, observes missing/invalid agent-auth and agent-token-to-MCP
audience denials, then invokes and reads the result through the official A2A
client. Its authorized transport permits only POST to the exact configured agent
URL and refuses redirects. The one explicit wrong-audience negative probe is
not a production MCP access path.

Positive acceptance requires one actual news item and the server's privately
verified same-user comparison. Empty news or failed delegation cannot produce
a success receipt. Output contains only item/comparison/denial/task-read counts;
no article text, tokens, claims or raw provider errors. This tool does not yet
exercise every live forbidden-workload case required by task 3.2.

### Local app/client evidence

The agent container was built locally with Podman, imported its six runtime
modules without development dependencies, and ran as UID/GID 65532. Seven live
container checks established liveness, truthful non-streaming discovery,
anonymous denial, wrong-host/origin denial, no server header and non-root
configuration. Its process/container were stopped afterward; no Azure call
or model invocation was made.

The combined [client](../tests/test_agent_client.py),
[runtime](../tests/test_agent_runtime.py), [operator](../tests/test_agent_control.py)
and existing platform-control selection passed **105 tests**. These include
actual loopback cleanup, local SDK A2A/OBO/MCP success versus empty/denied results,
PKCE/token/privacy failure paths, source-bound preparation/rollback, app-only
disable and drift refusal. All **115 typed files**, workspace lint and the
app layer's **10 mocked-provider cases** passed. These are local evidence, not
real browser/Entra sign-in, Azure readiness or live rollback proof.

### Complete offline pre-cloud gate

Task 2.3 passed the complete `bash scripts/check.sh` with an explicitly owned,
loopback-only PostgreSQL 18/pgvector helper: **941 tests passed** and only the
intentional live-publisher test was skipped. All database regressions ran.
The gate also passed lint/format, strict typing for **115 files**, isolated
package startup, feed/identifier validation, **11 strict OpenSpec items**,
validation of all **10 Terraform roots** and **66 mocked-provider cases**.
`uv build --all-packages` built all six wheels and source distributions.
The database helper was stopped and the owned local agent test image removed.

The first full attempt had **940 passing tests and one failure** in the
unchanged ingestion concurrency timing test: five feeds completed, but its
20-ms overlap observed three concurrent fetches instead of the expected four.
Two focused repeats and then the complete unmodified gate passed. The initial
failure receipt is retained privately; no ingestion implementation/test,
assertion, sleep or retry configuration was changed to obtain the pass.
This does not claim that the timing-sensitive test has been repaired.

No Azure provisioning, consent, ACR build, real sign-in/OBO or model call is
part of this gate. Task 3.1's private inventory, cost/permission review and
approved owning previews are next; group 4 stays blocked by actual task 3.2.

After the scope rename to `news.agent`, the focused agent/auth/delegation/client/
serving/identity and existing MCP regression selection passed **363 tests**.
Strict typing for **115 files**, workspace lint/format, **15 identity-layer
mocked-provider cases**, identifiers and all **11 OpenSpec items** passed.
Negative tests reject the former scope in caller tokens, registration adoption
and consent adoption.

Before requesting approval of the enabled identity preview, the subsequent
complete `bash scripts/check.sh` also passed after renaming: **944 tests passed**,
with only the intentional live-publisher test skipped. All database regressions,
115 typed files, lint/format, isolated startup, identifiers, 11 OpenSpec items,
10 Terraform roots and 66 mocked-provider cases passed. All six wheel/source
package builds passed again. The explicitly owned PostgreSQL helper was stopped.

### Approved image build and app-only preview

After separate approval for the agent-only ACR build and app preview, the
immutable `newsloom-agent` image built successfully in the retained registry.
Independent digest lookup and local source hashing matched:

| Binding | Value |
| --- | --- |
| Image input revision | `7e0d878812d82725e40f4a2f435e80b039f7084ebfa955f7aa4767d8e754434f` |
| Image digest | `sha256:a6d182fd21131c4451cfee59a2d04545d3bfd12a76ea675e5b127a53ce805edb` |

Native `azd provision agent --preview --no-prompt` passed with **one addition,
zero changes, zero deletions**. Independent plan inspection verified the retained
ACA environment, exact new identity, immutable image/source binding, one
0.25-CPU/0.5-GiB Consumption replica (maximum one), HTTPS ingress, all three
probes, empty browser origins and only the fixed non-generative runtime inputs.
The plan contains no database/model configuration or other service update.
No app apply was approved or executed.

Fresh read-only inventory still exactly matched all five existing workloads.
The retained chat catalog explicitly advertises chat completions for the pinned
model/version; regional DataZoneStandard allocation remains 110 of 1000 units.
These are compatibility/quota inventory, not actual inference or permission
exercise. A fresh count-only production data baseline remains required before
app deployment; prior Phase 1 counts are not presented as current observations.

The first full local attempt after the ARM-path fix did **not pass**:
**947 tests passed, one failed, one intentional live-publisher skip**.
The unchanged ingestion concurrency timing test again completed all five feeds
but observed only three overlapping fetches during its 20-ms sleep instead of
four. No assertion, test or ingestion runtime was altered to bypass that failure.
The earlier 944-test full pass and later 186-test focused pass remain separate
receipts, not substitutes for this failed latest attempt. The owned PostgreSQL
helper was stopped. Deployment was paused pending an explicit decision about a
deterministic test-only correction and another complete local gate.

### Approved deterministic local-test correction

With explicit test-only approval, the existing
[ingestion concurrency test](../tests/test_ingestion_database.py) now holds the
first four feed workers at an event before database I/O, rather than estimating
overlap with a 20-ms sleep. The entire run has a ten-second timeout. The exact
five-completed, maximum-four-active and zero-active-after-cleanup assertions
remain; production ingestion behavior is unchanged.

Verification after this correction:

- Four consecutive focused runs passed; all 22 ingestion database tests passed.
- A temporary in-process five-worker mutation failed the unchanged maximum-four
  assertion, demonstrating that synchronization does not conceal excess workers.
  No production file was mutated.
- The complete `bash scripts/check.sh` passed against an explicitly owned local
  PostgreSQL 18/pgvector instance: **948 tests passed, one intentional
  live-publisher skip**. Types passed for 115 source files; lint, format, isolated
  package startup, identifiers, strict specs and owning Terraform checks passed.
- `uv build --all-packages` built all six workspace wheels and source
  distributions. The local PostgreSQL helper was stopped and its removal verified.
- The image-input hash still equals the reviewed revision above. The test-only
  change requires no agent image rebuild.

The earlier failed attempts remain evidence, not passing receipts. This clears
the local blocker only. Separate approval for app provisioning and actual
signed-in OBO acceptance are still pending. Tasks 3.1 and 3.2 remain unchecked.

### Approved fresh production baseline and refreshed preview

With separate approval, exactly one execution of the existing migration job ran
only `enrichment-status`, not migrations or enrichment. Independent ARM readback
confirmed its successful execution, exact arguments and unchanged job definition,
identity and immutable image. Its correlated count-only receipt reports:

| Observation | Count |
| --- | --- |
| News / completed queue rows | 1,981 / 1,981 |
| Pending / processing | 0 / 0 |
| Failed queue rows | 1 |
| Retained dead letters / rejected records | 9 / 23 |
| Invalid vectors, completion mismatches, completed without news | 0 each |
| Duplicate URLs, duplicate source/GUIDs, published rejections | 0 each |

The failed queue row is an observed baseline condition, not a successful queue
outcome; it was not retried or modified. The status operation uses a read-only,
repeatable-read transaction with a 15-second statement timeout and emits no news
content.

The refreshed native agent-only preview again passed with **one addition,
zero changes, zero deletions**. Its complete planned app configuration and
unknown-value shape exactly match the earlier reviewed preview. The current
plan fingerprint is
`97c1f1dd38c1c0d529fb6fd71074798a472f407d88cd40c403022b4a5ba550c6`.
The immutable digest was independently found in the retained ACR again, and the
source-input hash still matches. No app apply has been approved or executed.

### Approved agent-only deployment and actual readback

After separate app-only cost/provisioning approval, native
`azd provision agent --no-prompt` completed with **one added, zero changed,
zero destroyed**. Independent ARM comparison confirmed all five existing
workloads' identities, images, configuration and schedules, plus all three
existing model deployments, were exactly unchanged. The resource count rose
from 18 to 19, adding only the approved agent app.

The first operator readback failed because the app ID and assigned-identity map
key used different casing for equivalent ARM paths. Five new local reproductions
failed before correcting the owning verifier to compare complete ARM paths
case-insensitively. It still rejects foreign/suffixed paths, duplicate identity
aliases and every original principal, image, configuration and probe mismatch;
UUIDs, permissions and other fields are not relaxed.

After that operator-only correction:

- All 135 related identity/control tests passed. The complete primary check
  passed **966 tests with one intentional live-publisher skip**, including types
  for 115 source files, lint/format, isolated startup, identifiers, strict specs
  and Terraform checks. All six workspace wheels/source distributions built.
  The explicitly owned PostgreSQL helper was stopped and its removal verified.
- Actual `verify-agent` passed for the sole assigned identity, immutable image,
  exact trusted runtime inputs, HTTPS/registry settings, one small Consumption
  replica, three probes and the ready revision.
- Actual HTTPS liveness returned 200. Official A2A discovery matched the
  non-generative recent-news contract, PKCE and `news.agent` scope. Missing and
  invalid authorization each returned 401. No signed-in invocation or model
  call was made.

The deployed image remains the approved digest and input revision recorded
above (`7e0d8788...`). The later local operator-only fix and README status updates
change the repository-wide input hash; they do not change agent runtime code or
replace the deployed image. These are distinct source states, not a claim that
the image matches the later checkout.
The source-binding guard remains enabled: a future app preview/update requires
an explicitly approved build matching its checkout. No additional build or app
update has been performed for this operator fix.

Task 3.1 is verified. Task 3.2 remains unchecked: real browser PKCE, user-preserving
OBO/MCP access and the remaining actual workload denials are still unverified.
Model-backed group 4 stays blocked.

### First actual browser attempt: sign-in incomplete

After explicit readiness approval, the real `verify-delegation` command started
its IPv4 loopback callback listener and browser sign-in. It exited with the safe
category `browser_sign_in_unavailable` before the client could invoke A2A/OBO.
The listener on port 8400 was confirmed closed afterward. That category alone
does not distinguish a callback timeout from an unavailable sign-in HTTP
dependency; browser/operator observations are needed before another attempt.
No token or authorization code is retained in the receipt.

This is a failed live sign-in attempt, not delegated-access acceptance. Task 3.2
remains unchecked, all model work remains blocked, and no alternate credential,
audience or data path was used.

### Windows-browser retry: actual user-preserving OBO passed

The operator observed no browser from WSL's default Python launcher (`gio`).
An explicitly process-local Windows launcher, without changing application
code, consent or redirect URIs, completed real browser sign-in and immediate
delegated A2A access successfully. For this WSL environment, the tested command
is:

```bash
uv run --env-file ".azure/<retained-environment>/.env" --locked --no-dev \
  --package newsloom-agent python - <<'PY'
import sys
import webbrowser
from newsloom_agent.cli import main

browser = webbrowser.GenericBrowser([
    "powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
    "Start-Process -FilePath '%s' -ErrorAction Stop",
])
webbrowser.register("windows-desktop", None, browser, preferred=True)
sys.argv = ["newsloom-agent", "verify-delegation"]
main()
PY
```

Only the client's generated trusted Entra authorization URL is handed to the
desktop browser. PKCE/state, the exact loopback callback, token validation,
memory-only credentials and the original bounded request behavior remain
unchanged. The callback listener was confirmed closed after success.

The actual client receipt reports **one real news item, one verified
user-preservation comparison, two agent-authorization denials, one
agent-token-to-MCP audience denial and one successful task read**. This proves
the deployed identity's secretless exchange and a real existing-MCP response;
it is not a local mock, operator-token forwarding or application-only read.
No article text, tokens, assertions or raw user identifiers are in the receipt.
No model call ran.

At this point task 3.2 was still incomplete: the agent's actual nondelegated MCP
and scoped workload denials remained to be exercised. Group 4 stayed blocked
until those required live checks also passed.

The operator approved the remaining bounded live permission-denial probes but
explicitly deferred their execution until returning the following day. No checks
were scheduled or run during that pause.

### Resumed live denial checks: delegation gate complete

On 2026-10-27 the operator resumed the approved checks. The deployed agent's
exact image, sole managed identity and ready revision passed independent
verification before and after the probes. Bounded execution used the existing
non-root agent container, not a new job, another workload or an operator bearer.
Tokens came only from its explicitly selected managed identity; tenant,
principal and client bindings were compared privately.

| Actual operation under the agent identity | Observed refusal |
| --- | --- |
| MCP `tools/list` with a nondelegated token | HTTP 403 |
| Existing embeddings deployment | HTTP 401 |
| Existing screening deployment | HTTP 401 |
| Existing chat deployment's Responses API | HTTP 401 |
| Foundry account management read | HTTP 403 |
| Foundry account key-list operation | HTTP 403 |
| PostgreSQL login using the agent identity's name | SQLSTATE `28P01` |
| PostgreSQL login as the existing MCP database role | SQLSTATE `28000` |
| PostgreSQL login as the existing administrator role | SQLSTATE `28000` |

The six HTTP probes accepted only 401/403 as denial and did not read response
bodies. The database probe used verified TLS and the actual server's SCRAM
negotiation, presenting the managed-identity token as the authentication
credential. It accepted only authentication-refusal SQLSTATEs and sent **zero
SQL queries**. The first auth-only attempt stopped on unsupported SCRAM before
the session-only probe gained that support; it was not counted as a denial
receipt. No dependency was installed in the container.

All nine required refusals passed. No inference succeeded, no data operation
ran, and no credentials, article text, response bodies or raw upstream errors
were exported. Private evidence retains safe statuses/comparisons and the probe
source fingerprint. The earlier real browser receipt separately establishes
successful user-preserving OBO/MCP access; these denials are not substitutes for
that positive proof.

Independent post-probe comparisons confirmed the agent definition/identity and
all five pre-existing workloads' identities, images, configuration and schedules
were unchanged, as were all three model deployments. The retained resource set
remains exactly 19. No role, consent, model capacity, job or resource changed.

Task 3.2 is now verified: **9/15 tasks complete**. Group 4's identity prerequisite
is satisfied, but model integration, streaming, final telemetry, subsequent
deployment/acceptance and publication remain pending. The last full local gate
is still the separate 966-pass/one-intentional-skip receipt above; no application
code changed during these live checks.

## Model stage: bounded generation and private telemetry

The completed live delegation gate allowed local work on tasks 4.1 and 4.2.
This section describes the model-stage implementation. Its separately approved
agent-only build/update is now deployed with independent readiness/configuration
verification; see the [deployment receipt](#approved-model-stage-build-and-deployment).
The earlier non-generative receipts remain historical evidence. The
[actual model-stage acceptance](#actual-model-stage-azure-acceptance) below
separately verifies signed-in Foundry streaming and telemetry ingestion.

### Fixed model path and A2A behavior

The [generator](../services/agent/src/newsloom_agent/generation.py) uses the
official Agent Framework `OpenAIChatCompletionClient`, not its Responses client,
over the existing Foundry-compatible `/openai/v1/chat/completions` endpoint.
Its explicit async OpenAI/HTTPX2 client uses the agent's managed identity for
`https://cognitiveservices.azure.com/.default`. It has zero retries, no tools,
no stored conversation, no proxy/environment credential discovery and no
redirect following. Incoming user/delegated tokens never enter that client or
the model messages. Caller metadata cannot override its options.

One successful delegated `get_recent_news(limit=1)` read supplies bounded,
typed metadata. Fixed developer instructions and untrusted news JSON are
separate messages. Nonempty news permits one generation with an actual wire
`max_completion_tokens=512`; an empty read emits an explicit no-news artifact
with zero generation calls. Failed OBO/MCP access cannot generate an answer.
This establishes a bounded demonstrator, not research or evaluated injection/
citation quality; those remain in [later capabilities](prd-2-capabilities.md).

The model stage adds a 32 KiB news-JSON input ceiling, a 16 KiB UTF-8 output
ceiling and a 128 KiB model-response wire ceiling to the existing
[request profile](#enabled-task-operations-and-finite-profile). The stream
also bounds provider updates. A finished response must include a normal stop,
nonempty output and observed usage within the output-token bound.
Refusals, tool calls, length stops, missing finish/usage, malformed data,
shared-quota HTTP 429 and partial-stream failures remain failures.

`SendStreamingMessage` forwards genuine model text as append updates on one
artifact. Its eight-event channel applies backpressure. `SendMessage` buffers
the same bounded generation and returns the completed task. Completion carries
a content-free receipt with outcome, item count, user-preservation comparison,
generation-call count and observed output tokens; artifacts contain the answer.
Partial artifacts can be retrieved, but a failed/cancelled task is never a
completed answer. Ownership, metadata-only listing and unsupported methods
remain unchanged.

The HTTP boundary alone reads the real disconnect channel and shares that
signal with the SSE listener. Authenticated requests track their own producer
tasks: disconnect cleanup does not depend on the SDK closing nested generators.
All provider work consumes the original request/authorization deadline.

### Runtime and owning app inputs

The [agent app layer](../infra/agent/main.tfvars.json) adds only:

| Runtime environment field | Existing owning output |
| --- | --- |
| `MODEL_ENDPOINT` | `MODEL_ENDPOINT` |
| `AGENT_CHAT_DEPLOYMENT` | `ENRICHMENT_DEPLOYMENT` |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | Existing authenticated telemetry routing |

These are trusted deployment inputs, not caller/model selections. The runtime
requires them; there is no new model, capacity, grant, database connection,
identity, job or schedule. The [operator verifier](../services/platform/src/newsloom_platform/agent_control.py)
expects this exact new configuration after the model-stage update; its previous
non-generative readback receipt remains historical evidence, not verification
of this checkout. Only a newly source-bound agent image can deploy this change.

The existing small one-replica profile remains unchanged. The model price review
and separately approved immutable build/app-only preview/update are recorded
below. Actual inference still requires a separately approved acceptance budget.

### Authenticated, content-free telemetry

The [agent telemetry](../services/agent/src/newsloom_agent/telemetry.py) exports
through explicit managed-identity Azure Monitor exporters, with offline storage
disabled. It records only fixed operation/surface/outcome/category labels,
duration, generation-call counts and **observed** input/output-token counts.
Missing usage on failure is marked unobserved, not presented as measured zero
cost. HTTP transport outcomes and execution outcomes are separate, so HTTP 200
carrying a failed A2A task is not reported as successful execution.

Agent Framework instrumentation is explicitly and stickily disabled, including
automatic attempts to enable sensitive-data capture. The trace exporter also
rebuilds every dependency span through a
[shared core privacy helper](../packages/newsloom-core/src/newsloom_core/telemetry.py):
fixed name/resource, validated allowlisted attributes, no events, links,
status descriptions, instrumentation scope or tracestate. MCP uses that same
helper with its existing field policy; it is not imported as an agent server
dependency and its deployed image has not changed.
Console dependency messages still pass through core's content-free handler.

Application Insights ingestion is delayed; the live receipt below verifies it
for this deployed revision. Local exporters and canaries do not substitute for
that Azure evidence.

### Explicit streaming acceptance client

After approval of the inference budget for this deployed revision, the same
deliberate PKCE sign-in flow supports:

```bash
uv run --env-file .azure/dev/.env --locked --no-dev --package newsloom-agent \
  newsloom-agent verify-streaming
```

This command deliberately permits one real generation, verifies streaming-card
parity, the two agent auth refusals and cross-audience MCP refusal, actual
artifact events, completed task/readback parity, one item, user preservation
and bounded observed output tokens. It emits safe counts only. Do not run it
without an approved inference budget. The earlier `verify-delegation` command
remains for the earlier non-generative profile and refuses a streaming-card
mismatch rather than silently generating.

The [WSL Windows-browser workaround](#windows-browser-retry-actual-user-preserving-obo-passed)
still applies; select `verify-streaming` instead of `verify-delegation`.
Tokens, model prompts/answers and callback data remain memory-only.

### Local model-stage evidence

[Generation tests](../tests/test_agent_generation.py) exercise the real pinned
connector and A2A SDK with local MCP/model transports. They prove an artifact
arrives over real loopback HTTP before generation finishes, exact input/output
byte and 512-token bounds, zero retries, no tool/endpoint authority, empty news,
dependency/refusal/partial failures, original deadlines, cancellation and closed
resources. Deterministic blocked-consumer tests establish the exact channel
backpressure threshold.

[Privacy tests](../tests/test_agent_privacy.py) run actual HTTP success,
OBO/MCP/model failure, invalid downstream expiry, overload and disconnect.
They also deliberately force sensitive framework instrumentation back on:
actual automatic SDK spans are observed before sanitization, and news, prompt,
completion, token, assertion, request-ID, exception and synthetic span canaries
are absent from exported spans, metrics and console output.
The [acceptance-client tests](../tests/test_agent_client.py) cover both truthful
profiles without contacting Azure.

The first complete primary gate exposed a regression in the existing MCP
automatic-span privacy test: direct generator use could enable default framework
instrumentation, and a temporary agent-test provider could become cached by the
MCP SDK. The generator now disables capture at its own boundary as well as at
application startup; temporary test tracers are isolated without changing the
existing MCP privacy assertions. The combined generator/agent-privacy/MCP-privacy
regression run passed **37 tests**.

The corrected `bash scripts/check.sh` passed **1,012 tests with one intentional
live-publisher skip**, strict types for **120 Python files**, lint/format,
isolated no-dev imports, configuration/identifier/OpenSpec checks and all
mocked Terraform suites, including **13 agent app cases**. `uv build
--all-packages` built all six workspace distributions and wheels. The explicitly
owned loopback PostgreSQL 18/pgvector helper was stopped and removed; its port
was verified closed.

These results verify tasks 4.1 and 4.2 and the local prerequisites of 4.3.
The following receipt completes 4.3; local canaries do not complete 4.4.

### Approved model-stage build and deployment

On 2026-10-27, read-only preflight confirmed the retained France Central
`gpt-5.4-mini` version `2026-03-17`, `DataZoneStandard`, capacity 10 and
chat-completions support. No model or capacity change was requested.
The public [Azure retail pricing API](https://prices.azure.com/api/retail/prices)
returned these exact non-batch, non-priority France Central Data Zone meters:

| Meter | USD per million tokens |
| --- | ---: |
| `5.4 mini Inp Dz` | 0.825 |
| `5.4 mini cd Inp Dz` | 0.0825 |
| `5.4 mini Opt Dz` | 4.95 |

These are Azure Data Zone prices, not Global Standard or direct OpenAI prices.
At those rates, 1,000 uncached input tokens plus the full 512 output-token
allowance cost approximately **USD 0.00336**. A 65,536-input/512-output example
costs **USD 0.05660**; observed-usage validation is not a prepaid billing cap.
Actual agreement prices, usage and taxes may differ. No inference was run
during this build/deployment step.

The operator separately approved one agent-only ACR build and native app-only
preview, then approved the exact preview before apply:

```bash
AZURE_DEV_USER_AGENT=microsoft_foundry_skill uv run --locked newsloom-platform build-agent
AZURE_DEV_USER_AGENT=microsoft_foundry_skill uv run --locked newsloom-platform prepare-agent-layer
AZURE_DEV_USER_AGENT=microsoft_foundry_skill azd provision agent --preview --no-prompt
# Only after approval of this exact preview:
AZURE_DEV_USER_AGENT=microsoft_foundry_skill azd provision agent --no-prompt
AZURE_DEV_USER_AGENT=microsoft_foundry_skill uv run --locked newsloom-platform verify-agent
```

The successful Linux/amd64 build used two vCPUs for approximately 52.427 seconds
with a 900-second timeout. The retail `Task vCPU Duration` meter is zero for its
first 6,000 shared-tier seconds, then USD 0.0001 per vCPU-second. Without assuming
unused free allocation, this build represents approximately **USD 0.01049** of
compute, excluding image storage and any agreement adjustments.

| Runtime provenance | Verified value |
| --- | --- |
| Build-input/source hash | `4e3290d2d03a2e9fb6fc340c39529c439383fc210cd1fef99bf518bcd1b1e2a9` |
| Immutable image digest | `sha256:3330932020ffdbd758298ea7a649989687427a704dceb0b02b519e5c1ad763d6` |
| Native preview | 0 add, 1 in-place agent change, 0 destroy |
| Native apply | 0 added, 1 changed, 0 destroyed |

The source hash binds the build input before this later status-documentation
update; it is not a Git SHA or a claim that subsequent documentation has the
same input hash. The existing corrected primary-gate and all-six-package build
receipts above remain the local evidence; native provisioning is not claimed
to have rerun that complete gate.

Only the agent image/source and the three documented runtime inputs changed.
The first immediate operator readback correctly failed while the new revision
was still activating and the previous revision remained ready. No predicate
was weakened: subsequent ARM readback found the new revision ready, its one
container running, zero restarts and the full exact image/environment/identity/
ingress/registry/probe/resource/scale configuration matching. The pinned
eight-module local runtime import check used about 130 MiB peak RSS; that is not
a loaded-service memory measurement or full generation acceptance.

Actual public HTTP checks passed: liveness 200, streaming card 200 with one
skill, and missing/invalid authorization both 401. Independent pre/post
comparisons found exactly the same 19 resources, five existing workload
definitions/identities/schedules and three model configurations/capacities.
MCP was not rebuilt or redeployed; no identity or grant layer was applied.
Private receipts retain the original failed readback, successful retry,
preview/apply, source/digest, configuration and preservation comparisons.

This deployment receipt verified task 4.3 at **12/15 tasks complete**, without
running inference. The following separately approved acceptance completes 4.4.

### Actual model-stage Azure acceptance

On 2026-10-27, the operator approved at most two model-backed A2A requests,
512 generated tokens and 120 seconds per request, plus read-only workload,
telemetry and stored-record verification. One count-only execution of the
existing migration job was used, not a migration or enrichment run.
No image, infrastructure, registration, consent, grant, model or capacity was
changed during acceptance. The runtime provenance remains the
[approved deployment's source hash and digest](#approved-model-stage-build-and-deployment),
not the later status-documentation input hash.

The first sign-in attempt ended with `browser_sign_in_unavailable` before any
agent/model request. Its listener closed. After explicit approval to reopen,
the Windows browser PKCE flow completed; credentials remained memory-only and
the callback listener closed again after acceptance.

| Actual signed-in case | Measured result |
| --- | --- |
| Discovery/schema/security parity | Pinned A2A client accepted the streaming card and separate `news.agent` contract |
| Missing/invalid agent authorization | Two HTTP 401 responses |
| Agent-audience token sent to MCP | Refused before tool access |
| Completed request | One delegated item, verified same-user comparison, one real Foundry generation |
| A2A output | 93 artifact events; completed task/artifact readback matched |
| Model usage | 282 observed input tokens, 96 observed output tokens |
| Completed client duration | Approximately 3.291 seconds |
| Cancellation | Acknowledged after model output began; 28 observed artifact events/153 bytes |
| Cancellation client duration | Approximately 0.901 seconds; retained task cancelled, never completed |

The completed answer's cited URL matched an independently read stored URL by
in-memory comparison. Read-only SQL snapshots under the existing MCP database
identity bracketed the A2A requests: both had **2,078 news records**, the same
selected record/URL fingerprints and an identical full stored-news metadata
fingerprint. News, prompts, answers, tokens, user identifiers and URLs were not
written to receipts. This operator verification is not a database path or
credential fallback available to the agent.

Actual authenticated Azure ingestion contained both execution outcomes. The
completed span reported one generation and 282/96 token usage; cancellation
reported one generation with usage absent, not a measured zero cost.
At the reviewed retail rates, the completed request's observed tokens represent
approximately **USD 0.00070785**, excluding cancelled/unobserved usage and other
charges.
All **36** returned execution/dependency spans had the rebuilt fixed name and
only allowlisted fields plus Azure's `_MS.ResourceAttributeId` reference.
Success/cancellation counters and usage-observation metrics were ingested with
only operation/outcome/category dimensions; input/output usage metrics existed
for success, not fabricated cancellation usage. The six actual agent console
records were structured and exposed only the existing safe diagnostic schema.
Application Insights local authentication remained disabled. These live
schema/ingestion checks complement, rather than replace, the hostile
automatic-instrumentation canaries verified locally.

Final probes under the deployed agent identity again observed:

| Forbidden operation | Actual refusal |
| --- | --- |
| Nondelegated MCP | HTTP 403 |
| Embeddings, screening and Responses API | HTTP 401 each |
| Foundry management read and key listing | HTTP 403 each |
| PostgreSQL login as agent identity | SQLSTATE `28P01` |
| PostgreSQL login as MCP/admin role | SQLSTATE `28000` each |

HTTP denial probes read no response bodies; the three database-denial probes
sent zero SQL queries. Independent read-only operator SQL is reported separately.
Readback matched the agent's original three narrow grants, unchanged chat-only
role permissions, registrations, exact federation and both delegated consents.
All four Phase 1 workload grants matched the retained owning grant contracts.
Exactly **19** resources remained; all five existing workload images,
identities, templates/schedules and all three model configurations/capacities
were unchanged. The exact deployed agent revision remained healthy.

The count-only job's actual execution arguments were independently verified as
`enrichment-status`. Its result was **2,078 completed/news**, pending/processing/
failed zero, **10 dead letters** and **24 rejections**. Invalid vectors,
completion mismatches, completed-without-news, duplicate URLs/GUIDs and published
rejections were all zero.
An initial comparison with the older 2026-10-26 baseline failed: that earlier
snapshot had 1,981 news, one failed item, nine dead letters and 23 rejections.
Rather than overwrite that evidence or alter history, count-only pipeline
summaries at 11:00 UTC established the current values **before** the 11:25 UTC
A2A requests. Those pre-invocation values matched the final readback; stored-news
fingerprints also matched across the actual requests. Active scheduled production
data was not incorrectly treated as frozen overnight.

Private evidence retains the failed sign-in, initial operator-probe/input
mistakes, older-baseline comparison, corrected actual results and final
16-gate receipt. No model retry beyond the two approved successful/cancelled
requests was made; no data was restored, rewritten or deleted. No owned listener
or remote probe remains running.

This live receipt verified task 4.4 at **13/15 tasks complete**.
The following publication receipt records subsequent delivery gates.
Full research, phase-wide quality evaluations and browser UI remain later slices.

## Verified implementation publication

On 2026-10-27, after local and actual Azure acceptance, the verified
implementation was committed and pushed as
[`1b8d4af01fd9a88d880d654c0d984bcdebed5c1f`](https://github.com/ikhemissi/newsloom/commit/1b8d4af01fd9a88d880d654c0d984bcdebed5c1f).
Its primary
[CI run 40500304977](https://github.com/ikhemissi/newsloom/actions/runs/40500304977)
completed successfully for that exact SHA. The required contributor trailer
is present. Unrelated prompt deletions/new customization skills, ignored
environment/state and private operator evidence were excluded.

Immediately before publication, the complete `bash scripts/check.sh` gate
passed again with the disposable loopback PostgreSQL service:

| Check | Actual result |
| --- | --- |
| Ruff lint/format | Passed; 204 files formatted |
| Strict types | 120 source files passed |
| Local tests | 1,012 passed, one intentional live-publisher skip; 144.28 seconds |
| CI tests | 1,012 passed, the same intentional skip; 38.35 seconds |
| Isolated package startup | Agent, enrichment and MCP checks passed |
| Catalogue, identifier and strict OpenSpec guards | Passed; 11 OpenSpec items |
| Terraform | All ten owning layers validated and mocked-provider suites passed |
| Workspace builds | All six packages produced source archives and wheels |
| Owned local PostgreSQL | Stopped/removed; loopback port closed |

CI is offline runtime/regression evidence, not another Azure acceptance run.
Publication caused no deployment, grant or model invocation. Runtime provenance
remains source-input hash
`4e3290d2d03a2e9fb6fc340c39529c439383fc210cd1fef99bf518bcd1b1e2a9`
and image digest
`sha256:3330932020ffdbd758298ea7a649989687427a704dceb0b02b519e5c1ad763d6`.
The hash binds the original build input, including its then-current README;
it is not a Git SHA or a claim that later status-only documentation has the
same conservative build-input hash. The immutable deployed code was not rebuilt
to reconcile documentation.

This implementation-publication receipt verified task 5.1 at **14/15 tasks
complete**. The following separate receipt closes 5.2 only after its own
exact-head CI passed.

## Verified evidence/status delivery

The separate documentation-only evidence/status receipt was committed and
pushed as
[`58afd2132d85f11531ee64dde11f20c70a5abd6f`](https://github.com/ikhemissi/newsloom/commit/58afd2132d85f11531ee64dde11f20c70a5abd6f).
Its primary
[CI run 40501029431](https://github.com/ikhemissi/newsloom/actions/runs/40501029431)
completed successfully for that exact SHA **before task 5.2 was checked**.
It updates this runbook, phase/capability/ADR status, README and checklist;
the production source, deployed configuration and runtime digest are unchanged.
Local receipt checks passed all 118 local links/anchors, 16 shell blocks,
identifier hygiene and all 11 strict OpenSpec items.

Task 5.2 is verified: **15/15 tasks complete**. Step 2.1's A2A and secretless
delegation slice is delivered, not a complete research agent or Phase 2.
Full research, frozen quality evaluations and the browser UI remain pending.
Archival was separately approved after the closure receipt passed CI, as
recorded below. Closure/status-only heads require their own exact-head
CI before publication is reported complete and do not replace runtime or
implementation provenance.

## Verified skeleton archival

The final delivery closure
[`8bf48bedc48d9a0298233b229a0b2c4930d97f69`](https://github.com/ikhemissi/newsloom/commit/8bf48bedc48d9a0298233b229a0b2c4930d97f69)
passed its own
[exact-head CI](https://github.com/ikhemissi/newsloom/actions/runs/40501562347).
On 2026-10-27, the operator then approved synchronizing the delivered specs.
Both purposes and all 13 requirement blocks matched their accepted delta
verbatim; all 12 main specs passed strict validation before moving the change.
The [archive](../openspec/changes/archive/2026-10-27-agent-skeleton/tasks.md#verified-archival)
retains all 15 checked tasks and links to the original acceptance evidence.
Archive commit
[`2c160e395bf2e0106a0d910c1118292da4f48cff`](https://github.com/ikhemissi/newsloom/commit/2c160e395bf2e0106a0d910c1118292da4f48cff)
passed its own
[exact-head CI](https://github.com/ikhemissi/newsloom/actions/runs/40559574136).
No runtime, environment/state, grant, model, schedule or stored data was changed;
no additional inference was performed.
