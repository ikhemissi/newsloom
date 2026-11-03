# Design

## Context

See [proposal](proposal.md) and [requirements](specs/architect-focused-briefing/spec.md).
The existing worker reviews a consistent seven-day snapshot, then creates
150-word batch notes, reduces those to 120-word thematic notes and expands them
to 900-1,100 narrative words. It has no architectural audience or explicit
materiality selection. Supplied enrichment summaries contain at most 100 words;
facts absent from them cannot be recovered by inventing details.

Core and browser validators both reject short full-coverage briefings. The
current published report has 1,026 summary words plus 82 TL;DR words, so simply
tightening every read validator would invalidate a previously accepted artifact.
The panel renders scope/status/cutoff/window/generation/read/cache information
before or around the TL;DR. Main-page applied-filter chips duplicate draft
controls, while separate research chips preserve meaningful submitted snapshots.

## Goals / Non-Goals

**Goals:** Specific architect-relevant signal, no padding, one healthy metadata
line, no duplicate browse badges, and compatible audited deployment.

**Non-Goals:** More sources, raw-article/web fetching, enrichment reprocessing,
personalized filters, new models/resources/grants, spend caps or evaluation replay.

## Decisions

### 1. Facts first, selection second, prose last

Replace batch prose compression with typed factual candidates linked to the
original constrained source IDs. Retain product/capability, concrete change,
explicit before/after when supplied, availability, numbers/units/versions,
limits and a concise relevance explanation. Separate reported facts from
conditional architectural implications.

Review every eligible record, but classify candidates as material, watch-only
or routine. A material item needs both a supported concrete change and a clear
architectural consequence; vendor hype or an arbitrary score alone is insufficient.
Prefer changes affecting model/platform choice, deployment, agent integration,
security/compliance, pricing, deprecation or implementation constraints.
Routine funding/promotions/unchanged capability are omitted unless the supplied
facts establish a concrete architectural impact.

Deduplicate the same event/product/version across publishers before synthesis.
Rank by supported practical impact and evidence confidence, not timestamp or
article volume. Preserve factual candidate fields through reduction/selection;
do not repeatedly replace them with tiny generic thematic paragraphs.
Respect existing token/response/deadline limits and fail explicitly on genuine
processing failure, never silently sample only a page of input.

Use existing notes/reduce/summary/tldr operation labels to preserve accounting
and SQL stage contracts. Adapt source-ID schema enumeration/validation to every
new typed candidate leaf rather than assuming only DraftParagraph contains sources.
Test this wiring directly; JSON-schema shape changes must not weaken citation
membership. Revision hashing must include editorial instructions/policy.

### 2. Decision-useful output and a derived TL;DR

Each selected change leads with a specific named event, then its supported delta,
why it matters and essential caveats. Prefer actionable conditional guidance
such as evaluating a deployment option for stated constraints, not unsupported
claims that it is production-ready, faster or cheaper.

The TL;DR summarizes the completed selected briefing, names the highest-impact
changes and adds no new facts. Do not start with "AI is evolving", "agents are
gaining momentum" or generic governance/adoption commentary.
Missing metrics/version/availability remain unknown or omitted; explicit
preview/announced status must not become GA. No previous-version comparison or
"first ever" claim is inferred solely from the current publication date.

### 3. Estimated reading ceiling, compatible policy version

New architect-policy artifacts have no prose minimum. Combined TL;DR plus
summary narrative is at most 1,000 words, excluding headings/citations, with
200 words/minute as an explicitly estimated five-minute ceiling.
Preserve the existing concise paragraph TL;DR shape without a forced minimum;
derive actual reading-time cues rather than a fixed "About five minutes".
Few meaningful changes should yield a few specific paragraphs.

Add an optional recognized `editorial_policy` discriminator to the public
artifact, setting it explicitly on every new architect-policy publication.
Old artifacts without it retain their historical validation rules and remain
readable; newly generated artifacts cannot opt out into legacy rules.
Both Core and browser validation enforce the new combined budget consistently.
An unsupported policy value fails, rather than silently accepting a different shape.

`full` describes completed input review, not a long output or an obligation to
mention every article. `limited` remains honest evidence/processing limitation,
not a way to evade an arbitrary lower word bound.

### 4. No material signal is not no news

Introduce `coverage: "no_material_changes"` for a successfully reviewed,
nonempty corpus with no selected material candidates. It has positive
evidence_count, no generated sections/citations and no fabricated TL;DR.
The controller/panel displays a concise fixed notice that no material changes
were identified in reviewed stored reporting. This is not a claim about the
whole world, a failure-shaped fallback or a new ordinary paragraph with an
irrelevant citation added just to pass validation.

Preserve existing `empty` for genuinely zero eligible news, and distinct
failure/unavailable states. No-material publications use the new policy;
legacy readers cannot receive them until compatible Core/API/UI are deployed.
The payload is already JSONB, so this outcome does not require runtime DDL or
a new persistence resource. Refusal, malformed output or incomplete processing
still fails normally and cannot become a no-material result.

### 5. Presentation reduction, not loss of operational truth

For a healthy artifact, remove the scope paragraph, "ready" status, expected
cutoff/window/count and read/cache-age display. Keep one compact generation
timestamp immediately before the TL;DR. Retain those values in the protected
DTO/operational records, not a replacement expanded diagnostics block.

Show short stale/read-failure/unavailable/no-news notices only when applicable,
with necessary read-only retry controls; do not expose raw error data.
Keep safe citations in the collapsed full content. Preserve the panel heading/
Close control, research notice after briefing, independent scrolling and focus.

Remove only the main `Applied news filters` section and its spacing. Reuse
FilterChips for research context without deleting shared CSS/helper code.
Keep explicit draft/Apply/Search semantics and the existing unsent-change help;
removing badges must not silently make draft controls automatically applied.
Completed/in-flight answer context stays frozen.

### 6. Test editorial value, not only valid JSON

Add authored evidence/oracles with named material changes and routine distractors:
breaking API/SDK behavior, deployment/licensing constraints, preview versus GA,
pricing units, same-event duplicates, unsupported comparisons and all-routine weeks.
Verify expected inclusions, exclusions and preservation of supplied facts across
map/selection/reduction/summary/TL;DR. A schema-valid generic trend essay must fail
quality assertions. Retain source-injection and citation controls.

Test measurable 1,000/1,001 combined-word boundaries, valid short full reports,
legacy 1,026+82-word read compatibility, explicit no-material versus empty/failure
and policy handling. Browser/component checks verify visible order/geometry and
removed metadata/badge spacing, including narrow screens and frozen research
context. Authored tests do not replace actual user quality review in Azure.

## Risks / Trade-offs

- Stored summaries may omit the desired specificity -> preserve available facts
  and disclose critical uncertainty; never fabricate or fetch full articles in this slice.
- Selection can omit a valuable item -> authored relevance oracles and user review;
  retain input counts/provenance and avoid claims of exhaustive real-world coverage.
- Tightening length/outcomes breaks old artifacts -> recognized editorial policy,
  legacy read compatibility and consumer-first rollout.
- Removing chips hides an applied snapshot while controls contain drafts -> retain
  explicit Apply/help and immutable research context, not automatic behavior changes.

## Migration Plan

Before implementation, reconcile the parent's active planning requirement/
design/owning PRD capability from forced 900-1,100-word visible-window overview
to the approved selective policy; preserve historical measured results and
unverified acceptance. No parent artifacts are edited during this proposal turn.

Deploy compatible API/shared contracts and UI first, then the new worker policy.
Existing artifacts remain available until the next valid 05:00 UTC slot
publishes the refinement; that is this slice's default verification path.
Preserve all prior attempts/costs and do not delete a successful daily artifact
or bypass its guard. A same-day editorial replacement is not added here: a
later explicit request would need its own audited operation/approved scope
before dispatch, rather than silently reusing failed-run retry authority.

Use fresh immutable images/owning native azd previews and local gates, with no
new resources or permission changes. Verify served UI geometry/assets and an
actual produced architect-focused report against the agreed quality rubric.
Rollback restores compatible images/policy without rewriting history or
claiming missing scheduled/semantic/signed-in acceptance.
