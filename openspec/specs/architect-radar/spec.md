# architect-radar Specification

## Purpose
Show each reader what needs action, what is worth knowing and what can wait,
from stored announcements, personalised by the products they follow.

## Requirements

### Requirement: Model triage of announcements
Each announcement SHALL receive one tier (`act_now`, `worth_knowing`, `later`),
a reason of at most 20 words and a capability topic of at most 4 lowercase words
from a model call that reads only the item's stored title, summary, article kind,
announcement statements, statuses, dates and product names. Invalid triage output
SHALL leave the announcement untriaged and counted, without failing enrichment.

#### Scenario: A new item is enriched
- **WHEN** an item with announcements is published
- **THEN** its announcements are triaged in the same enrichment run and the triage
  call never receives article text

#### Scenario: Triage fails
- **WHEN** the triage call fails or returns output outside the schema
- **THEN** the news item and announcements are still published, untriaged
  announcements appear under "Worth knowing", and a backfill can triage them later

### Requirement: Reader stack and card state
A signed-in reader SHALL be able to read and replace their stack (at most 50
vendors or products) and mark an announcement Done, Snoozed for 7 days or
active again. State SHALL be keyed by a pseudonymous reader key derived from
tenant and object ID, readable and writable only by that reader, and never
returned to other readers.

#### Scenario: Card state is set
- **WHEN** a reader marks an announcement Done
- **THEN** it no longer appears on their radar, still appears for other readers,
  and their choice persists across devices

#### Scenario: Snooze expires
- **WHEN** seven days pass after a reader snoozed an announcement
- **THEN** it appears on their radar again in its tier

#### Scenario: Caller without object ID
- **WHEN** a token without an object ID calls a reader route
- **THEN** the request is rejected with 401 and nothing is stored

### Requirement: Personalised radar ranking
The radar SHALL return announcements from a requested window (7 or 30 days) in
three tiers. Without a stack, the model tier is used. With a stack, `act_now`
SHALL be kept only for announcements naming a stack product or vendor, or whose
item kind is security or regulation; other `act_now` items move to
`worth_knowing`. Within a tier, stack items come first, then nearest deadline,
then newest. Done and active snoozed announcements are excluded.

#### Scenario: Security outside the stack
- **WHEN** a security announcement does not name a stack product
- **THEN** it stays in "Act now"

#### Scenario: Same capability across vendors
- **WHEN** announcements from two or more vendors share a capability topic in
  the same tier and window
- **THEN** they are returned as one group with each vendor's announcement

### Requirement: Product timeline and deadlines
The API SHALL return a product's announcements across all sources in date
order with their item links, and upcoming deadlines (next 90 days, from "Act
now" and "Worth knowing" announcements only) ordered by date, both read-only
and without article text.

#### Scenario: Product page
- **WHEN** a reader opens a product
- **THEN** its canonical name, vendor, aliases, related products and
  announcements are shown, so name matching can be reviewed

### Requirement: Radar home page
The default signed-in page SHALL show the briefing header, the three tiers
(the third collapsed), a deadlines strip and links to product pages, with
Done, Snooze, Follow and "Ask about this" actions on each card. The previous
list SHALL remain available as "All news" at `/news`, and item URLs are
unchanged. The page follows the existing accessibility and clutter-free rules.

#### Scenario: Keyboard use
- **WHEN** a reader uses only the keyboard
- **THEN** every card action and tier toggle is reachable with visible focus and
  axe reports no violations on desktop and mobile widths

### Requirement: Clickable briefing citations
Each TL;DR and briefing citation marker SHALL be a link to its source article
(new tab, safe HTTPS only), without requiring the reader to expand the briefing.

#### Scenario: Reader checks a TL;DR claim
- **WHEN** the reader activates a TL;DR citation marker
- **THEN** the cited source opens directly
