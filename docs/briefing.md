# Daily news briefing

Status: worker, protected API and panel UI deployed as early access in the
[owning change](../openspec/changes/archive/2026-11-07-daily-news-briefing/tasks.md). The corrected
job runs daily at 07:45 UTC for the 05:00 UTC slot, after the database wakes
([operations runbook](operations.md)). A first full artifact was published by an
explicitly authorized controlled retry on 2026-11-03; actual scheduled execution
and signed-in qualitative acceptance remain open. Earlier failed attempts and
their costs remain in append-only history and the original call rows.
The [architect-focused refinement](../openspec/changes/archive/2026-11-07-architect-focused-briefing/tasks.md)
is now deployed consumer-first. Its new editorial policy takes effect at the
next valid 05:00 UTC slot; deployment does not rewrite today's successful report.
[PRD-3](prd-3.md) owns sequencing; [capabilities](prd-3-capabilities.md) own
product behavior. The [news API](news-api.md) and [UI runbook](ui.md) own their
existing transport and browser boundaries.

## What readers receive

One shared English briefing is produced daily for the 05:00 UTC slot; the job
starts at 07:45 UTC, after the database wakes. Its fixed evidence
window is the preceding seven days, ending exclusively at that scheduled
cutoff. Delayed execution does not move the window. Future-dated records and
later ingested records are not silently included in that frozen snapshot.
Browsing filters, selected articles and the reader's timezone do not customize
the artifact.

Architect-policy reports have no prose minimum. Combined TL;DR and summary
narrative is at most 1,000 words, an estimated five-minute ceiling at 200 words
per minute; fewer meaningful changes produce shorter reports, not padding.
Legacy publications retain their historical 900-1,100-word narrative read policy.
Empty evidence publishes a no-news state without generation. A nonempty review
with no material architectural signal publishes a distinct no-material notice.
These are synthesized stored summaries and metadata, not full articles or
exhaustive coverage of real-world news.

The worker first produces the cited summary, then derives a concise TL;DR from
that completed summary in the same run. Both publish atomically. The panel
shows the TL;DR above an accessible full-summary collapsible, closed by default.
Reading or expanding never starts generation or sends an agent question.

The editorial audience is an AI solution architect. Generation first retains
named products, supported concrete changes, exact source spans for versions/
metrics/limits, availability, caveats and conditional architectural implications.
Every input UUID must be represented in the review. Only explicit material
signals reach consolidation/synthesis; routine promotion, funding without
practical design impact and generic trend commentary are omitted.
Same-event reports are consolidated and ordered by practical impact/confidence.
Selection must fit useful explanations within the reading ceiling, rather than
turning every article into an item. Facts survive structured reduction instead
of being repeatedly compressed into generic thematic prose.

Ranking uses impact, then the number of independent reports, never product-name
order, and allows at most three items per vendor. Reports about the same product
are merged into one item. Security incidents and compromised releases are always
material. Named customer case studies are not padded into prose: they appear as
one line each in a final "Customer case studies" section, with the main services
in parentheses (kept only if named in the source). Vendor showcases without a
customer are excluded. Individually unsupported or duplicate items/paragraphs are
dropped instead of failing the whole report; invented numbers are still rejected.

Source-ID schema constraints cover factual candidates and review lists as well
as final paragraphs. Protected spans must exist in their cited stored evidence;
GA/preview claims need explicit source support. Summary validation rejects
missing selected products/change/implication/protected facts; a generic
schema-valid essay is not a successful briefing. These controls are not a
substitute for actual semantic/user review, and missing source details are
never invented or recovered through unapproved full-article fetching.

New artifacts carry `editorial_policy: "architect-v1"`; unknown policy values
are rejected. Legacy artifacts without a policy remain readable and serialize
without an extra null policy field, allowing consumer-first rollout. A
`no_material_changes` artifact has reviewed news but no generated TL;DR, body
or irrelevant citations. The UI shows a concise fixed notice instead.
Healthy presentation keeps only generation time before the TL;DR, with brief
exceptional stale/failure notices and no read/cache/window diagnostic block.

## Local preview

Iterate on prompts and selection without deploying. Export the week's stored news
as `{"items": [...]}` files (for example from the read-only MCP `search_news` tool
in chunks under its 50-item limit), then run:

```sh
bash scripts/briefing-preview.sh --input week-*.json --cutoff 2026-11-04T05:00:00+00:00
```

It runs the production pipeline with your Azure CLI identity, never writes to the
database, and writes `briefing.md`, `briefing.json` and `recording.jsonl` under the
ignored `.cache/briefing-preview/`. Add `--replay .cache/briefing-preview/recording.jsonl`
to reuse recorded stages and run only the stages after them; a TL;DR-only rerun
takes seconds and costs well under a cent. A full week costs roughly USD 0.10.
`tests/test_briefing_golden.py` replays a synthetic recorded week with the model
mistakes seen in production; extend it when a new failure mode appears.

## Execution and publication

The dedicated `newsloom-briefing` workload uses managed identity, the existing
database/ACA environment and a separate deployment of the pinned enrichment
chat model/version. Existing model deployments/capacity stay unchanged.
No A2A user session, OBO token, embedding or web-search operation is needed.
Core async ModelClient transport is reused with a fixed model endpoint and
deployment, strict structured output, no tools and content-free diagnostics.
Source IDs are also restricted by a per-stage JSON-schema enumeration, with
post-generation membership checks retained. Request admission includes the
enumeration's token cost; reduction continues when necessary to fit synthesis.

The worker's isolated tokenizer counts model input/schema tokens for bounded
batching rather than treating every byte as a token and needlessly turning the
week into tiny one-minute calls. Its pinned encoding is cached during image
build, so runtime generation does not download tokenizer data. Context headroom,
completion allowance and serialized rate pacing respect the verified deployment.

The new workspace member changes the root manifest/lock fingerprints but no
existing locked service dependency closure. The evaluator's production-input
guard therefore adds an explicit V3 fingerprint set including the briefing
manifest. Original V1/V2 pins and digest readback remain accepted unchanged;
old provenance receipts still require their exact historical digest. This
does not restart a baseline, rebind an old approval or rewrite evaluation usage.

Every eligible public news row enters a consistent read-only snapshot, not a
20/50/200-item UI/API sample. Bounded map/reduce stages consider all input;
context, response, convergence or deadline failure fails the run explicitly.
Original source IDs and URLs resolve all published references. Structural
citations are not semantic faithfulness proof; qualitative acceptance is
recorded separately.

One durable run row claims each cutoff. A session advisory lock prevents
overlapping execution; a unique cutoff prevents duplicate daily generation.
Intent is durable before each model operation. Confirmed throttling can retry
within the original deadline, but uncertain generation is not replayed.
A lost run remains failed/unknown, retains previous content and does not
silently reset its usage. Later daily slots may proceed.

The application stores only the latest protected artifact and metadata-only
run/call accounting. Intermediate notes, evidence bodies, prompts, completions
and credentials never enter logs, traces or job output. No historical briefing
browser or saved conversation is added.

## Authority and migrations

Only versioned migrations create the additional briefing principal/tables and
grants. Existing migration checksums and the foundation's original four-entry
identity manifest remain intact.

| Principal | Allowed | Explicitly not allowed |
| --- | --- | --- |
| Briefing writer | Public news projection SELECT; own run/call/current-artifact reads/writes; registry pull; chat inference; scoped telemetry | News modification, database administration, embeddings, registry push |
| Existing MCP workload | Current briefing and safe status projection SELECT | Briefing generation/writes, writer identity, new model privileges |
| Browser | Existing delegated news.read API access | Direct database/model access, regeneration or writer credentials |

Actual service RBAC scope may be account-wide for the chat operation; a fixed
client deployment does not establish deployment-scoped RBAC isolation. Owning
readback and real-role tests must record the supported scope honestly.

### Briefing history

Every published briefing (scheduled or revised) is appended to `briefing_history`
(migration `008`) in the same transaction that publishes it, so past versions stay
available for evaluation and for reader feedback. The writer can insert and read
history rows but not update or delete them; the MCP role can read them. The
migration backfilled the then-current briefing and the briefings superseded by
guarded revisions; earlier daily briefings had already been overwritten.

## Read API and freshness

`GET /api/v1/briefing` returns `{briefing, refresh, meta}` under the existing
news API authorization/origin/no-store policy and shared admission capacity.
No new browser scope or consent is required. Authenticate/authorize before
every cache hit. The response includes the artifact's immutable window/version/
generated-at, safe structured text/citations, expected cutoff, state and stale
flag. Cache identity includes the expected cutoff, with the existing absolute
60-second maximum lifetime.

Null artifact, a valid empty-week artifact, pending/running refresh, stale last
good content and API/service failure remain distinct. A failed daily update
does not erase last good content or rewrite its dates. API failure remains an
error, not a successful no-news fallback. Browser reads do not alter question,
filters, selected news, answer context or server-reported cache age.

## Measurement, not a spending cap

The first successful controlled retry considered 90 stored articles and published
a 1,026-word summary plus an 82-word TL;DR with 42 citations. Across the two
retained failed attempts and the successful attempt, actual accounting records
12 physical model calls, 44,700 input tokens and 11,595 output tokens, with
estimated model cost USD 0.09427275 and zero unknown operations. The successful
attempt alone accounts for USD 0.072625575; hosting/build costs remain separate.
Numeric/provenance validation is not a semantic faithfulness or user-review score.
That controlled-retry worker source was
`abce35e2d3a7421f7ce83780bb54b4376fc81f40cc4fad7100fc4a94c4f76de1`;
its earlier UI/API source associations remain recorded in the rollout history.

The notes stage had produced incomplete output at its earlier 1,400-token
allowance. It now has a 4,096-token allowance with smaller input batches and
exact schema/input-token admission to stay within the deployment's verified
rate envelope. Truncation is explicitly categorized, and known failed attempts
can be retried only by the guarded operator command.

There is no daily dollar cap in this slice. Measure actual physical calls,
input/output tokens, latency and estimated model cost using a dated price
basis. Missing usage remains unknown, not zero. Hosting, registry/build and
other infrastructure costs are separate and may be unmeasured.
Use observed production behavior to decide a future policy, not an arbitrary
initial limit.

Read-only preflight on 2026-11-02 found the existing pinned gpt-5.4-mini
2026-03-17 DataZoneStandard available in the retained region, with regional
allocation 110/1,000 before adding briefing capacity 10. Its advertised rate
at capacity 10 is 10 requests/10,000 tokens per minute. Azure retail meters
showed USD 0.825 input and USD 4.95 output per million tokens; cached-input
discounts are not assumed. Recheck availability/quota/price at deployment,
and record actual usage rather than interpreting these as incurred costs.

## Architect refinement rollout (2026-11-03)

Compatible API/shared contracts and the concise UI were deployed and independently
verified before updating the scheduled producer. All three immutable images have
source revision
`e163fbad78462cb383a465efaa229f2a3a2e54377ff3d1834638431d130bb9aa`.
Native previews showed only three in-place image changes and the UI runtime
revision. Exact before/after ARM readback preserved all eight workload
configurations, all four model deployments and 19 feature/authority flags,
apart from those approved image/revision fields. No migration, resource,
permission, consent or model-capacity change was needed.

The full scoped primary gate passed: 303 evaluator tests, 1,741 repository
tests with the intentionally excluded live-publisher test skipped, 78 UI tests,
18 pinned browser journeys, strict types/lint, OpenSpec and native Terraform
checks. All workspace packages built. A pinned nonroot production build matched
the served index and both script/CSS assets byte-for-byte, with identical runtime
configuration. API readiness 200, anonymous briefing denial 401 and exact-origin
preflight 204 passed. Actual Azure anonymous desktop/mobile checks had no
horizontal overflow, script errors, protected requests or axe violations.

A non-generating inspection under the new worker parsed the actual legacy
publication and returned the identical before/after metadata and usage receipt:
90 records, 1,026 narrative words, 82 TL;DR words, 42 citations and 12 physical
model calls with no unknown usage. No new generation was dispatched. This proves
legacy read compatibility, not new editorial quality. The next valid daily slot,
actual specificity/materiality/citation review and permitted signed-in browser
acceptance remain open; neither this change nor its parent is archived.
Implementation commit `a99a411` passed exact-source
[CI 41730799877](https://github.com/ikhemissi/newsloom/actions/runs/41730799877).
All 52 unrelated parked paths remained byte-preserved through publication.

## Recovery and acceptance

After explicit user authorization, `newsloom-briefing retry-failed` can retry a
known validation failure in the same day. It archives the failed run metadata in
an append-only table, leaves original call/cost rows intact and continues their
ordinals. It refuses running/successful slots, existing same-slot artifacts and
unknown usage. The fixed publication window remains; a new consistent snapshot
is recorded for the retry. This is an operator action, never a read/expand/API
side effect. Original scheduled duplicate protection remains unchanged.

Do not delete failed history or relaunch uncertain generation to repair missing
answers. Reconcile current artifact/run status read-only; preserve unknown
usage. Known validation failures require the explicitly authorized guarded
operator retry; a subsequent daily slot remains independent.

### Guarded editorial revision

The [guarded refresh](../openspec/changes/archive/2026-11-05-guarded-briefing-refresh/tasks.md)
adds an explicitly authorized operator command for replacing today's published
artifact, for example after an editorial-policy change:

```sh
newsloom-briefing revise-published --request-id <new-uuid> \
  --expected-version <current-artifact-version> --reason editorial-policy-upgrade
```

Obtain the current version from `newsloom-briefing inspect`, which reports only
safe metadata. If today's scheduled slot failed with a known validation category
and fully observed usage, a revision can also supersede it while the older
report stays published until the replacement validates. Admission locks generation, requires the expected version and
fully observed usage, and refuses reused request IDs or an execution that could
overlap the next 05:00 UTC cutoff. Before dispatch, the prior payload and run
metadata are inserted into the writer-restricted append-only
`briefing_revisions` table (migration `007`); MCP/readers cannot access it.
Call ordinals continue and all earlier call/cost rows stay intact. The existing
artifact remains published until the new summary and TL;DR both validate and the
base version is still current. A failed revision keeps last good content;
another attempt needs a fresh request ID and no unknown usage. The window stays
fixed, though the new snapshot may include late rows for that window. A manual
revision is not evidence of scheduled execution. Ordinary `run` and
`retry-failed` behavior is unchanged.

Provision only owning native azd layers after local/real-role checks and
reviewed previews. Bootstrap one manual slot before enabling `45 7 * * *`.
An observed manual run proves neither actual scheduling nor signed-in browser
acceptance; keep those tasks open until measured.

On 2026-11-03, an initial startup attempt exposed a missing async identity
transport dependency; the isolated production closure and startup check were
corrected before generation. An actual writer-identity access probe then
verified news-write denial and zero prior runs/calls/current artifacts.
The first model generation was correctly rejected for an unrecognized citation
ID, with no artifact published: 89 eligible records were snapshotted, one model
call used 6,577 input and 940 output tokens, and its estimated model cost was
USD 0.010079025. Usage was observed with zero unknown operations; hosting/build
costs remain separate and unmeasured.

The user subsequently directed immediate correction and deployment. Citation
choices were constrained at every generation stage, but the failed daily slot
and its usage were preserved rather than regenerated. Successful generation and
qualitative acceptance remain open until a new daily slot produces a validated
artifact. Enabling the corrected next scheduled slot is an explicitly reported
sequencing exception, not a claim that the initial manual generation passed.

The Terraform provider treats manual-to-scheduled triggers as replacement.
Transition therefore recreates only this slice's newly-created briefing job,
retaining its name, dedicated identity, model, grants, profile and database
run/accounting records. Original workloads, identities, models and schema are
not destroyed or recreated. Preserve job-execution metadata before transition;
the database ledger remains authoritative for once-only dispatch and usage.

Original worker/UI rollout source:
`6ea37bee8a0564eeef5d4cd3a7c8e38f2411afc0577c8244fe71072943443c17`.
The deployed API retains its independently verified image/source association:
`a063f364dcfdbe6fb82433f3689f00834d3ecba34bfe58afae99df5239758551`.
Owning scheduled-job and UI readbacks passed; the three served script/CSS assets
matched the pinned production build byte-for-byte. API readiness 200,
anonymous denial 401 and exact-origin preflight 204 passed. Anonymous Azure
desktop/mobile shell checks had no overflow, script errors or axe violations
and dispatched no protected requests. These are not signed-in briefing proof.

The post-transition writer probe found one run, one call and no current
artifact, confirming that the failed attempt was retained and not retried;
news-write denial still passed. All four other original app/jobs and all three
original model deployments retained their fingerprints. The canonical dev
state was reconciled only after an independent-change check.
Combined implementation and measured-deployment publication `ddfd957` passed
exact-source CI `41690057706`. This does not close successful-generation,
actual-scheduled or signed-in quality acceptance.

Rollback first disables the briefing schedule, then restores matching API/UI
images. Preserve identities, tables, run records and all existing jobs/models.
Never recreate the environment or rewrite migration history.
