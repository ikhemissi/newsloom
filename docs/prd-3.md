# PRD-3: Agent UI

Status (2026-11-15): the web app is deployed early access with the architect
radar, news browsing, item and product pages, the daily briefing, research
conversations with web research, reader feedback and read-only overnight mode.
Most slices are archived with signed-in evidence; checks that could not run are
listed in [known gaps](known-gaps.md). Full phase acceptance still needs Step
3.15 and the Phase 2 [agent baseline](prd-2.md).

On 2026-10-31 the user approved delivering the browser journey before Phase 2's
evaluations were complete; this early-access exception still applies.

This document owns phase sequencing and capability-to-slice assignments.
[Capabilities](prd-3-capabilities.md) own behavior, user stories, acceptance
criteria, future-work boundaries, and unresolved product decisions.
See [the ADRs](adrs.md) for technical choices.

## Delivery plan

| Step | Slice | Capability scope |
| --- | --- | --- |
| 3.1 | `ui-spike-and-shell` | [P3-C01](prd-3-capabilities.md#p3-c01-browser-sign-in-with-organizational-identity), [P3-C06](prd-3-capabilities.md#p3-c06-supported-ui-integration-and-verified-azure-hosting), and minimal [P3-C02](prd-3-capabilities.md#p3-c02-streaming-research-chat)/[P3-C03](prd-3-capabilities.md#p3-c03-visible-navigable-article-citations)/[P3-C05](prd-3-capabilities.md#p3-c05-inert-rendering-and-accessibility-basics): sign in, ask, progress, validated answer, citations; not an empty shell |
| 3.2 | `ui-news-feed` | [P3-C07](prd-3-capabilities.md#p3-c07-news-feed-search-and-item-context): latest-news landing, top MCP search and closable right-hand A2A panel with current-news context; remaining [P3-C02](prd-3-capabilities.md#p3-c02-streaming-research-chat)/[P3-C03](prd-3-capabilities.md#p3-c03-visible-navigable-article-citations)/[P3-C05](prd-3-capabilities.md#p3-c05-inert-rendering-and-accessibility-basics) context/rendering |
| 3.3 | `ui-news-filters` | [P3-C04](prd-3-capabilities.md#p3-c04-source-category-and-date-shortcuts), filtering in [P3-C07](prd-3-capabilities.md#p3-c07-news-feed-search-and-item-context): explicit source/category/local-calendar browsing and structured A2A constraints |
| 3.4 | `cached-news-api` (archived) | Same MCP app, delegated `news.read` and workload identity; authorize before every cache lookup; 60-second bounded cache, detail and browse cursors |
| 3.5 | `ui-http-news-catalog` (archived) | HTTP news catalogue, shareable stored-item pages, explicit Load more capped at 200 items |
| 3.6 | `daily-news-briefing` (archived) | [P3-C08](prd-3-capabilities.md#p3-c08-shared-daily-weekly-news-briefing): shared seven-day briefing, TL;DR and collapsed full summary |
| 3.7 | `architect-focused-briefing`, `guarded-briefing-refresh` (archived) | Briefing focused on material architectural changes; audited same-day revision |
| 3.8 | `user-feedback` (archived) | [P3-C09](prd-3-capabilities.md#p3-c09-reader-feedback): ratings and comments on briefings and answers, reviewer queue, eval cases |
| 3.9 | `full-article-acquisition`, `announcement-graph` (archived, PRD-1 data) | Article text and announcements linked to products and vendors, feeding the radar |
| 3.10 | `architect-radar-home` (archived) | [P3-C10](prd-3-capabilities.md#p3-c10-architect-radar): radar home page, followed products, product pages |
| 3.11 | `nightly-operations`, `read-only-overnight` (archived) | Daily export, night stop, read-only snapshot and browser state |
| 3.12 | `research-conversations` (deployed, user check open) | Conversation panel, last three turns as context, suggested follow-ups |
| 3.13 | `web-research` (deployed, user check open) | Web IQ search in discovery mode, separate web citations |
| 3.14 | `snapshot-refresh` (deployed) | Read-only snapshot refreshed every 30 minutes during the day |
| 3.15 | Phase tests and versioned evaluations | [P3-C05](prd-3-capabilities.md#p3-c05-inert-rendering-and-accessibility-basics)/[P3-C06](prd-3-capabilities.md#p3-c06-supported-ui-integration-and-verified-azure-hosting) deployed acceptance; then the versioned [Phase 2 baseline](prd-2.md) |

Use [the development guide](development.md#openspec) to execute each slice.
