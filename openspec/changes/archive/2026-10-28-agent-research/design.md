# Design

## Context

See [the proposal](proposal.md#why) for motivation and
[PRD-2](../../../../docs/prd-2.md) for phase ownership.
The [delivered A2A](../../../specs/a2a-serving/spec.md) and
[delegation](../../../specs/delegated-mcp-access/spec.md) contracts remain the
baseline. This active change defines the extension; the
[runbook](../../../../docs/agent.md#state-constrained-actual-acceptance) owns measured
implementation and Azure acceptance evidence. Publication remains a separate gate.

Skeleton extension points before research:

- The skeleton accepts the literal `recent-news`, reads exactly one item
  through `DelegatedMcp.recent`, and uses `RecentNews(max_length=1)`.
  `RecentAgent`, the card and the PKCE client all enforce that fixed shape.
- `FoundryGenerator` uses the pinned official chat-completions connector with
  tools disabled, no retries and one generation. Its single-call guard must not
  be weakened to implement another operation.
- The task registry, eight-event queue, request-owned producer and cancellation
  middleware already provide bounded transient A2A lifecycle handling.
- MCP exposes four tools. Search can embed queries using **MCP's** identity.
  Detail adds author/date-origin/publisher categories, not full article text.
  Source/category/tag/date/limit validation and result DTOs already exist on the
  server; the agent needs independent typed client contracts, not server imports.
- Existing transport/privacy tests use actual loopback A2A/MCP and model-wire
  transports, with cancellation and automatic-instrumentation canaries.

## Goals / Non-Goals

**Goals:** add a small request-scoped research controller; preserve delivered
authorization and recent-news behavior; enforce tool/filter/citation boundaries
in code rather than trusting prompts; expose evidence limits honestly.

**Non-Goals:** persistent memory, a generic workflow engine, public web access,
raw-article retrieval, new inference authority or a quality claim based only on
valid JSON and URLs. Deferred product work belongs to the
[PRD TODOs](../../../../docs/prd-2.md#deferred-research-todos).

## Decisions

### 1. Add an explicit request contract, not implicit conversation recovery

Add a `research` skill with a single JSON data part containing
`operation: "research"`, a nonblank question, optional `item_ids`, optional
source/category/tags/from/to filters, and optional language/audience/detail/focus
preferences. Reject unknown fields and extra parts before model/tool calls.
Use timezone-aware explicit dates; relative-date wording in the question does
not authorize silently guessed hard filters. The acceptance client gains an
explicit research command that builds this contract. The literal text operation
`recent-news`, its limits and returned result remain unchanged.

Selected-item mode accepts one to five distinct UUIDs. Fetch those records
directly through MCP before model planning; do not broaden discovery to replace
missing selected items. If no selection is provided, allow constrained discovery,
recent browsing and search. Filters remain authoritative in both modes.
Preferences affect presentation only; language/audience/focus strings have finite
lengths, and detail is an explicit brief/detailed choice.
Explicit content and quotation requirements in the question take precedence
over these presentation preferences. In particular, `detail=brief` must not
silently excerpt or paraphrase an explicitly requested complete stored summary.
This priority never changes caller filters, evidence availability, permissions
or budgets: unavailable full articles remain unavailable, and a request that
cannot fit the existing limits must fail explicitly rather than silently omit
required content. The user confirmed this priority after the first live
full-summary/brief conflict; its failed acceptance receipt remains retained.
Do not derive persistent preferences from prior tasks or treat context IDs as
conversation memory. A new request retrieves its own evidence again.

**Alternative:** interpreting arbitrary old plain text as research would change
the delivered unsupported-input behavior and make structured selection/filters
ambiguous. An explicit additive operation is easier to validate and test.

### 2. Keep the model-selected loop application-owned and finite

Use the existing Agent Framework chat-completions connector with an explicit
controller, not an unrestricted SDK auto-tool loop. Up to three structured
planning responses may select bounded batches of the four fixed MCP operations
or request synthesis. A separate final synthesis is at most the fourth model
call. Closed schemas contain operation choices and typed arguments, never
executable code, endpoint configuration or a free-form reasoning transcript.
Disable provider/SDK retries and automatic tool invocation. Validate the pinned
connector's structured-response wire shape with local transports first.

For each planning turn, derive a frozen typed scope from validated request and
evidence state plus remaining budgets, never from instructions in questions,
preferences or retrieved strings. Build the closed planning schema from that
application-owned scope. Detail-ID choices must be known before the turn starts;
omit detail lookup when no legal known IDs exist. Preserve independent call
batches, but require a later planning turn for detail calls that depend on newly
discovered IDs. A placeholder or predicted ID cannot stand in for a tool result.

Permit synthesis when detail evidence is available, or permit stopping after a
healthy empty retrieval so the controller returns no-match without final
generation. Metadata or a source listing alone cannot justify synthesis.
Budget exhaustion must still fail explicitly when required detail is missing;
state-constrained planning neither expands the profile nor manufactures evidence.

Validate the complete returned plan against the same frozen scope before
dispatching any call from it. Retain every existing per-call authorization,
selection, filter, duplicate and budget guard independently of provider schema
enforcement. Invalid or provider-nonconforming plans fail explicitly, without ID
substitution, repair generation, retries or widened budgets. Request-local
schemas and known IDs remain excluded from diagnostics.

The dispatcher owns the tool allowlist and copies immutable caller constraints
into reads. Refuse attempted constraint relaxation rather than silently relaxing,
clamping or retrying. Model-selected detail IDs must be selected by the caller
or already discovered in this request. Reject unknown tools, foreign IDs,
malformed/oversized arguments, repeated identical calls and aggregate overrun
before execution. Never use server-selected schemas or remote references as
authority.

**Alternative:** a deterministic retrieval pipeline would give less control over
which discovery/search/detail steps help a particular question. A general
autonomous loop would add unbounded cost and obscure request ownership.
Prompt-only tuning was insufficient in the retained live attempts: one plan
chose synthesis with only metadata, and a later plan attempted an unknown
detail ID. Those failures remain recorded in the
[runbook](../../../../docs/agent.md#current-candidate-state-aware-planning-decision-remains-open).
The user approved state-constrained planning; the
[follow-up receipt](../../../../docs/agent.md#state-constrained-actual-acceptance)
records its local and actual signed-in checks without relabeling prior failures.

### 3. Extend the delegated session without changing authority

Factor only the request-local exchange/session mechanics out of the existing
recent reader. Research owns one downstream session and token validated for
the same tenant/object caller and exact `news.read` permission. All sequential
calls reuse that request's identity and the smaller of caller/token/original
deadlines. Validate fixed local input/output DTOs for each operation and the
identity-bearing token before tool use. Never cache user tokens across requests.

Keep the agent independent of the MCP server package. Add only the DTOs required
for source discovery, ranked metadata, detail/not-found and constrained search;
retain existing MCP regression tests and public schemas. Treat invalid results
as failures, not empty collections. Compare returned metadata against filters.
For inconsistent versions of the same stored item within a request, fail
explicitly instead of combining conflicting citation evidence.

**Alternative:** one OBO exchange per tool adds avoidable work; sharing a global
session leaks user state. Direct SQL or a new agent embedding grant would violate
the delivered boundary. Semantic search stays behind the existing MCP identity.

### 4. Use a separate research budget profile

Retain the existing body/text, four-request, 64-task, five-minute retention,
single-replica and original 120-second deadline controls. Research has these
additional application-enforced limits; none widens the recent-news profile:

| Boundary | Proposed maximum |
| --- | --- |
| Question | 8 KiB UTF-8 |
| Language / audience / focus preference | 64 / 256 / 1,024 UTF-8 bytes |
| Selected IDs | 5 distinct IDs |
| Tool operations | 8 sequential calls, including application-selected detail reads |
| Recent/search results per call | 5 items |
| Unique evidence records | 10 |
| MCP response wire bytes | Existing 128 KiB per response, 512 KiB aggregate |
| Model requests | 3 planning calls and 1 final call; no repair/retry calls |
| Generated tokens | 512 per planning call, 2,048 final, 4,096 aggregate ceiling |
| Current model input/history | 64 KiB serialized UTF-8 per call, 256 KiB aggregate |
| Raw model response wire bytes | 128 KiB per call, 512 KiB aggregate |
| Validated answer plus rendered citations | 16 KiB UTF-8 total |
| Stream events | Existing bounded queue of 8 |

Check exact-boundary and one-over cases, including normalization/serialization.
Do not silently discard evidence or reset accounting after a tool/model turn.
Reserve the final model-call/output allowance before admitting planning.
No evidence after a healthy retrieval produces explicit absence without a
final model call. Invalid plans or incomplete outputs fail without self-repair.
Unknown cancelled usage remains unknown, never recorded as zero.

Before cloud execution, measure peak RSS with four simultaneous near-limit
requests; require it below 400 MiB on the existing 512 MiB replica and verify
cancellation/backpressure. Stop for review rather than resizing or weakening
limits if the profile cannot pass. Price both chat turns and possible MCP-side
query embeddings at current regional meters. Byte/call ceilings are finite
bounds, not a prepaid dollar cap or proof that shared quota is available.

**Alternative:** raising every old limit would alter the accepted demonstrator;
per-turn-only limits allow a bounded turn to become an unbounded workflow.

### 5. Validate citation structure before exposing the answer

Final synthesis returns a closed structure with outcome, claims carrying
supporting evidence IDs, explicit limitations, missing selected IDs and selection
coverage. It contains no model-selected citation URLs. Application code checks
shape, IDs, nonempty support on news claims, coverage and final size, then resolves
citations from the exact current evidence records. Require safe absolute HTTPS
URLs without credentials/control characters; never fetch them.

State insufficient evidence when summaries lack requested detail. Missing items
are not operational failures, but coverage must be explicitly partial; a tool or
model failure still fails the task rather than serving earlier successful data.
Render plain text from the validated structure with exact stored citation URLs.
Schema/provenance checks cannot prove semantic entailment; focused authored
cases and independent manual live review check claim support. Step 2.3 retains
the separately frozen phase-wide quality set and thresholds.

**Alternative:** validating arbitrary generated Markdown URLs after token emission
cannot prevent already exposed fabricated citations. Automatic repair would
add cost and hide a failed validation attempt.

### 6. Stream safe progress, then buffered validated answer chunks

Reuse A2A status/task/artifact machinery. Before validation, send fixed phases
such as retrieving/synthesizing/validating with safe counts only, never raw plans,
tool arguments/results or draft text. Buffer the bounded final structure,
validate, then emit the rendered answer in bounded artifact chunks.
The card and client must say this is progress followed by validated answer
streaming, not unvalidated live token streaming.

Keep completion/readback parity, caller ownership, disconnect cancellation and
cleanup under the same authorization/deadline. Cancellation during planning,
MCP, final drafting, validation or emission cannot become completed work.
Do not extend diagnostic allowlists with questions, preferences, item IDs, URLs,
tool bodies or model content. Aggregate safe call/token/usage observations across
turns and exercise both framework and dependency instrumentation canaries.

**Alternative:** provisional token streaming was rejected by the user in favor of
validated delivery. A separate durable task service is unnecessary here.

## Risks / Trade-offs

- **Summaries lack requested detail:** explain the gap; do not simulate web or
  full-article access. The future toolbox work remains an explicit TODO.
- **Injection can influence model choices or claims:** hard tool/constraint/URL
  boundaries prevent authority changes; hostile semantic cases still need tests.
- **New card/schema breaks the strict old acceptance client:** extend its
  discovery validation for implemented additive skills while retaining tests
  for the exact recent-news payload, counts and denial behavior.
- **Active scheduled data changes during verification:** compare news metadata
  around the request and actual time-correlated pipeline history, not an
  overnight frozen-count assumption.
- **More turns add latency/cost and memory:** enforce the profile; verify local
  concurrency and current chat/embedding quota before executing any live run.

## Migration Plan

1. Implement typed contracts/structured connector tests, delegated research
   session and controller behind a default-off `research_enabled` setting.
   Keep recent-news unchanged; prove failed/disabled paths have no work.
2. Wire citation validation, truthful card/client, bounded progress/answer
   delivery and safe aggregate telemetry. Run focused hostile/cancellation/
   citation/constraint cases, the complete primary gate and all workspace builds.
3. Inventory the unchanged environment, actual grants/model availability/quotas,
   resource/workload/schedule/data baselines and metered request envelope.
   Under the user's 2026-10-27 standing Step 2.2 authorization, execute one
   immutable build and native agent-only preview, review the exact change set,
   then apply only that owning change. No shared or MCP image update and no
   additional approval prompt is required within this scope.
4. After readiness/image/configuration readback, define and enforce a small live
   signed-in acceptance envelope under the same authorization, covering selected single/multi-item research,
   constrained discovery/search, no-match/detail limits and cancellation.
   Check user preservation, citations against independent stored metadata,
   telemetry and actual workload denials. Retain all failed attempts honestly.
5. On failure, leave gates unchecked and disable research or restore only the
   prior agent revision through reviewed retained-state changes. Do not repair
   data, broaden permissions or alter another workload.
6. Publish only verified implementation with exact-SHA CI, followed by separate
   evidence/status receipt and its exact-head CI. Mark only Step 2.2 complete.
   Propose Step 2.3 separately; archive only after all measured gates pass.
