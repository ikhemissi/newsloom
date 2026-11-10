# Known gaps

Acceptance checks that could not run are recorded here instead of keeping their
change active indefinitely. They are **not** verified; archiving a change does not
claim they passed. See the
[delivery contract](../openspec/specs/repository-foundation/spec.md#requirement-honest-ordered-delivery).

Most gaps need a signed-in session in the user's regular browser. Automated
browser checks run anonymously or against local fixtures, and the project does
not export user tokens or browser state to automation.

| Change (archived) | Unverified check | Why it could not run | What did run |
| --- | --- | --- | --- |
| `ui-news-filters` | 4.4 Relevant results for combined source/category/date and search filters | Run on 2026-11-07, see below: a search for "agentcore" returned unrelated items | Component, browser and anonymous Azure checks; signed-in filtering ran |
| `nightly-operations` (active) | Read-only data while the database sleeps (00:00–08:00 Paris) | Needs its own change; the web app shows errors overnight | Exports, stop and wake |
| `nightly-operations` (active) | Schedules follow Paris winter time only | Container Apps cron is UTC; in summer every time is one hour later in Paris | — |
| `cached-news-api` | 4.3 Search cache hit on a repeated identical query; TTL | Signed-in run produced briefing hits but no search hit | Authorized HTTP routes and delegated MCP search succeeded on 2026-11-07 |

## Signed-in run, 2026-11-07

The user ran one signed-in pass in their regular browser. Verified: feed, Load
more, item detail and source link; local timestamps; toolbar (a Custom dates
selection wraps one button, accepted); keyboard use; research with citations and
an answer rating; narrow-window news list; sign-out returns to the sign-in
prompt. Telemetry showed only successful authorized API calls, with briefing cache
hits and misses. This closes the signed-in checks of `ui-spike-and-shell`,
`ui-news-feed`, `ui-http-news-catalog`, `ui-compact-news-toolbar`,
`ui-browser-local-timestamps` and the review in `guarded-briefing-refresh`.

Findings, tracked as product work rather than gaps:

- The briefing is "a beginning but not very useful" and leans towards AWS.
- TL;DR citations are not clickable; checking a source needs several steps.
- Search relevance: "agentcore" returns unrelated items.
- A research answer appears below the fold, and follow-up questions have no
  conversation model.
- On narrow screens the research panel sits at the bottom of the page.

Close a gap by running the check and recording its outcome here, or by adding an
automated check that covers it.
