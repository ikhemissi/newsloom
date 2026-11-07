# Spec Delta

## Purpose

Acquire the article page for every new item so stored text contains the actual
news, while staying within robots, content-signal and politeness rules.

## MODIFIED Requirements

### Requirement: Protected single-response article recovery
Article acquisition SHALL use at most one article GET per item per retrieval
attempt, with verified public HTTPS, pinned DNS, robots policy and bounded
bytes/time. Article redirects MUST NOT be followed. Acquisition MUST NOT execute
scripts, fetch assets, resolve remote JSON-LD contexts, navigate
canonical/alternate links, rewrite hosts, or bypass sign-in or paywalls.

#### Scenario: An article redirects
- **WHEN** the direct article response is a redirect
- **THEN** no request is made to its Location target
- **AND** the item keeps its feed text, records a safe acquisition outcome and its usable siblings continue

#### Scenario: A destination or body violates policy
- **WHEN** an article or robots request targets a prohibited address, is disallowed,
  or exceeds its byte/time budget
- **THEN** no policy bypass or unbounded work occurs and the outcome is explicit

### Requirement: Ordered missing-field recovery
For every new item that is not filtered and not a known duplicate, ingestion
SHALL attempt one article acquisition. Feed identity fields (title, canonical
URL, GUID, publication dates) remain authoritative; article metadata MUST NOT
replace them. Missing title/text SHALL still be filled from JSON-LD/OpenGraph and
then visible article content. The stored text SHALL be the visible article body
when it is usable and substantially longer than the feed or metadata text,
otherwise the feed text. Ingestion MUST NOT generate summaries. Selected text
MUST pass the existing scanner before acceptance and stays bounded by the
existing text limit.

#### Scenario: Feed fields are sufficient
- **WHEN** an item already supplies a usable title and text
- **THEN** one article acquisition is still attempted and the feed identity
  fields are used unchanged whatever its outcome

#### Scenario: Structured metadata supplies the missing fields
- **WHEN** JSON-LD/OpenGraph completes an incomplete feed item
- **THEN** usable feed fields remain unchanged and the metadata path is recorded
- **AND** no second article request or model summarization is performed

#### Scenario: Metadata lacks usable article text
- **WHEN** metadata supplies a headline or only a short description, and the same
  HTML contains readable article content
- **THEN** ingestion uses the visible content, records the article-body path and
  submits bounded publisher text to the unchanged scanner

#### Scenario: A feed teaser hides the article
- **WHEN** a feed item has a short description and the article page has a much
  longer readable body
- **THEN** the bounded article body is stored, the article-body path is recorded
  and feed identity fields are unchanged

#### Scenario: Feed text is already complete
- **WHEN** the article body is not substantially longer than the feed text
- **THEN** the feed text is kept and the feed-item path is recorded

#### Scenario: Acquisition is not possible
- **WHEN** robots or content signals deny the article, the request fails,
  redirects, or the page has no readable body (for example script-rendered)
- **THEN** the item is stored with its feed text, the outcome category is
  counted, and an otherwise valid item is not rejected

#### Scenario: A known duplicate or filtered item is encountered
- **WHEN** identity or publisher-category information establishes that the item
  is already durable or outside the configured filter
- **THEN** it is counted accordingly and no article request occurs

#### Scenario: Text recovery fails for an otherwise valid title-only item
- **WHEN** the item still satisfies the existing normalization contract but no
  additional article text can be obtained
- **THEN** the failed acquisition is explicit and empty text alone does not newly
  invalidate an entry that the existing title-only contract permits

## ADDED Requirements

### Requirement: Cached robots and content signals
Ingestion SHALL fetch robots.txt at most once per host per run and reuse that
decision for the rest of the run. Existing robots semantics (missing file allows,
other non-success denies) are unchanged. A `Content-Signal` line applying to the
`Newsloom` group or `*` that sets `ai-input=no` SHALL prevent article
acquisition for that host; feed text remains usable.

#### Scenario: Many items from one host
- **WHEN** a run acquires several articles from the same host
- **THEN** robots.txt is requested once for that host in the run

#### Scenario: A site refuses AI input
- **WHEN** a host's applicable group declares `Content-Signal: ai-input=no`
- **THEN** no article request is made to that host and items keep feed text
- **AND** the denial is counted with a fixed category

#### Scenario: A site allows AI input but not training
- **WHEN** a host declares `ai-input=yes, ai-train=no`
- **THEN** acquisition proceeds, because article text is only used as model
  input and is never used for training

### Requirement: Polite identified acquisition
Article requests SHALL identify Newsloom with a descriptive user agent that
includes the public project URL, SHALL make at most one concurrent request per
host, and SHALL honour `Retry-After` on 429/503 within the job deadline; a
host that is still throttled defers its remaining items to a later run. The
user agent MUST NOT imitate a browser.

#### Scenario: A host throttles
- **WHEN** an article request returns 429 or 503 with `Retry-After`
- **THEN** no further request is sent to that host before the delay, and items
  that cannot complete in this run are deferred, not dropped

### Requirement: Bounded recent-item backfill
An explicit operator command SHALL acquire articles for already stored items
published within the last 14 days, using the same acquisition, robots,
content-signal, politeness and selection rules, at most once per item. It SHALL
only update the stored queue text of those items; published news identity and
summaries are unchanged.

#### Scenario: Backfill runs
- **WHEN** the operator runs the backfill
- **THEN** only items from the last 14 days without acquired article text are fetched,
  outcomes are counted per category, and a second run makes no new requests

### Requirement: Internal bounded article retention
Acquired article text SHALL be used only as model input and MUST NOT be exposed
through UI, HTTP or MCP responses, logs or telemetry. Article text older than
90 days SHALL be removed from completed queue entries while feed text and
derived fields remain.

#### Scenario: Retention runs
- **WHEN** an ingestion run finds completed entries whose article text is older than 90 days
- **THEN** the article text is removed, feed text and published news are unchanged,
  and only counts are reported
