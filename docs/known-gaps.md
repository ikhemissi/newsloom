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
| `ui-spike-and-shell` | 5.4 Signed-in research/progress/citation journey, deployed keyboard/axe while signed in, live authorization failure | Needs the user's regular-browser sign-in | Local/pinned browser journeys, anonymous Azure axe, API/agent readbacks |
| `ui-news-feed` | 1.1 Prerequisite ledger of `ui-spike-and-shell` (now archived with the gap above); 4.4 signed-in feed/search/panel/citation journey | Same as above | Component, browser and anonymous Azure checks |
| `ui-news-filters` | 4.4 Signed-in source/category/date and combined-search journey with applied A2A constraints | Same as above | Component, browser and anonymous Azure checks |
| `cached-news-api` | 4.3 Authorized deployed HTTP/MCP parity, warm-cache denial, TTL and semantic hit/miss counts | Needs a delegated `news.read` user token | Real-role database tests, anonymous 401, readiness, exact-origin preflight |
| `ui-http-news-catalog` | 3.4 Signed-in HTTP news/filter/search, Load more, detail navigation and A2A context | Same as `ui-spike-and-shell` | Component and pinned browser journeys, asset parity, anonymous Azure axe |
| `ui-compact-news-toolbar` | 2.3 Signed-in toolbar alignment and accessibility | Same as above | Local journeys, anonymous Azure desktop/mobile axe, asset parity |
| `ui-browser-local-timestamps` | 2.3 Signed-in timestamp/offset/future-label behavior | Same as above | Component tests, local browser journeys, asset parity |

Close a gap by running the check and recording its outcome here, or by adding an
automated check that covers it.
