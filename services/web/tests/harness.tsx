import { createRoot } from "react-dom/client";
import { App } from "../src/App";
import { parseAnswer } from "../src/answer";
import type { AuthSession, ResearchClient } from "../src/domain";
import { UiFailure } from "../src/domain";
import { architectBriefing, briefing, legacyBriefing, noMaterialBriefing, newsItem, sourceCatalog, newsDetail, page, runtimeConfig } from "./fixtures";
import { matchesFilters } from "../src/filters";
import { HttpCatalog } from "../src/catalog";
import { HttpFeedback } from "../src/feedback";
import { FixtureRadar } from "./radar-fixture";
import type { FixtureCard } from "./radar-fixture";
import "../src/style.css";

document.documentElement.dataset.researchCalls = "0";
document.documentElement.dataset.searchCalls = "0";
document.documentElement.dataset.querylessCalls = "0";
document.documentElement.dataset.recentCalls = "0";
document.documentElement.dataset.sourceCalls = "0";
document.documentElement.dataset.briefingCalls = "0";
const parameters = new URLSearchParams(location.search);
const displayedItem = parameters.has("future-date")
  ? { ...newsItem, publishedAt: "2026-11-03T00:00:00Z" } : newsItem;
window.history.replaceState(null, "", parameters.get("route")
  ?? (location.pathname.startsWith("/news/") ? location.pathname : "/"));
let catalogueAttempts = 0;

const auth: AuthSession = {
  signedIn: () => true, signIn: async () => undefined, signOut: async () => undefined,
  token: async () => { throw new Error("Authored harness never acquires tokens"); },
};
const briefingHttp = new HttpCatalog(runtimeConfig, {
  ...auth, token: async () => "authored-briefing-token",
});
const feedback = parameters.has("feedback") ? new HttpFeedback(runtimeConfig, {
  ...auth, token: async () => "authored-feedback-token",
}) : undefined;
const research: ResearchClient = {
  async *ask() {
    document.documentElement.dataset.researchCalls = String(
      Number(document.documentElement.dataset.researchCalls) + 1,
    );
    yield { kind: "progress", phase: "retrieving" };
    const paragraphs = parameters.has("long")
      ? Array.from({ length: 60 }, (_, index) =>
        `Authored long paragraph ${index + 1}. This fixture checks independent panel scrolling without live research.`).join("\n\n")
      : "<img src=x onerror=bad()> [1]";
    yield { kind: "answer", answer: parseAnswer(
      `${paragraphs}\n\nLimitation: authored UI fixture only.\n\n[1] https://publisher.test/article`,
    ) };
  },
  stop: async () => false,
};
const radarCard = (id: string, change: Partial<FixtureCard>): FixtureCard => ({
  id, news_id: `https://publisher.test/${id}`, title: `Authored item ${id}`, url: `https://publisher.test/${id}`,
  source: "fixture-source", published_at: "2026-11-07T10:00:00Z", article_kind: "announcement",
  statement: `Authored statement ${id}.`, status: "ga", effective_date: null, deadline: null,
  products: [{ name: `Authored product ${id}`, vendor: "Authored vendor" }], tier: "worth_knowing",
  reason: `Authored reason ${id}.`, capability: "other", ...change,
});
const radar = parameters.has("radar") ? new FixtureRadar([
  radarCard("a", { tier: "act_now", article_kind: "security", statement: "Patch <img src=x onerror=bad()> now.", deadline: "2026-11-30" }),
  radarCard("b", { capability: "agent tools" }),
  radarCard("c", { capability: "agent tools", products: [{ name: "Other tool", vendor: "Other vendor" }] }),
  radarCard("d", {}),
  radarCard("e", { tier: "later" }),
], () => new Date("2026-11-08T12:00:00Z")) : undefined;
const container = document.getElementById("root");
if (!container) throw new Error("Missing fixture root");
function batch(cursor?: string) {
  const start = Number(cursor?.replace("page_", "") ?? 0);
  return page(Array.from({ length: 20 }, (_, offset) => ({
    ...newsItem, id: newsItem.id.slice(0, 24) + String(start + offset).padStart(12, "0"),
    title: `Authored page item ${start + offset + 1}`,
  })), start + 20 < 240 ? `page_${start + 20}` : null);
}
createRoot(container).render(<App auth={auth} research={research} feedback={feedback} radar={radar} catalog={{
  briefing: async (signal) => {
    const calls = Number(document.documentElement.dataset.briefingCalls) + 1;
    document.documentElement.dataset.briefingCalls = String(calls);
    if (parameters.has("http-briefing")) return briefingHttp.briefing(signal);
    if (parameters.has("briefing-error") && calls === 1) throw new UiFailure("unavailable");
    const result = parameters.has("briefing-architect") ? architectBriefing()
      : parameters.has("briefing-legacy") ? legacyBriefing()
        : parameters.has("briefing-no-material") ? noMaterialBriefing() : await briefing();
    if (parameters.has("briefing-pending")) result.briefing = null;
    if (parameters.has("briefing-empty") && result.briefing) result.briefing = {
      ...result.briefing, coverage: "empty", evidence_count: 0, tldr: null, sections: [], citations: [],
    };
    if (parameters.has("briefing-stale") || parameters.has("briefing-pending")) result.refresh = {
      expected_cutoff: "2026-11-03T05:00:00Z", stale: true, state: calls === 1 ? "running" : "failed",
    };
    if (parameters.has("briefing-version") && calls > 2 && result.briefing) result.briefing = {
      ...result.briefing, version: ["2f763497", "93cc", "42d7", "a560", "37eb80a7509e"].join("-"),
      tldr: { text: "Authored updated weekly overview.", references: [1] },
    };
    return result;
  },
  recent: async () => {
    document.documentElement.dataset.recentCalls = String(
      Number(document.documentElement.dataset.recentCalls) + 1,
    );
    return parameters.has("paged") ? batch() : page([displayedItem]);
  },
  detail: async (id) => parameters.has("missing") ? null : ({ ...newsDetail, ...displayedItem, id }),
  sources: async () => {
    catalogueAttempts++;
    document.documentElement.dataset.sourceCalls = String(catalogueAttempts);
    if (parameters.has("catalogue-error") && catalogueAttempts === 1) throw new UiFailure("unavailable");
    return parameters.has("hostile-catalogue") ? {
      ...sourceCatalog, categories: sourceCatalog.categories.map((category) => ({
        ...category, label: "<svg onload=bad()>",
      })),
    } : sourceCatalog;
  },
  search: async (_query, _signal, filters = {}, cursor) => {
    document.documentElement.dataset.searchCalls = String(
      Number(document.documentElement.dataset.searchCalls) + 1,
    );
    if (_query === undefined) document.documentElement.dataset.querylessCalls = String(
      Number(document.documentElement.dataset.querylessCalls) + 1,
    );
    if (parameters.has("paged") && _query === undefined) return batch(cursor);
    return page([{ ...displayedItem, title: "Authored search result" }].filter((item) => matchesFilters(item, filters)));
  },
}} />);
