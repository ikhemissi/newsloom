import type { RuntimeConfig } from "../src/config";
import type { BriefingResponse, NewsDetail, NewsItem, NewsPage, SourceCatalog } from "../src/domain";

export const runtimeConfig: RuntimeConfig = {
  tenantId: crypto.randomUUID(), clientId: crypto.randomUUID(),
  agentUrl: "https://agent.test/a2a", agentScope: `api://${crypto.randomUUID()}/news.agent`,
  newsApiUrl: "https://mcp.test/api/v1", newsScope: `api://${crypto.randomUUID()}/news.read`,
};
export const newsItem: NewsItem = {
  id: crypto.randomUUID(), title: "Authored news headline", summary: "Authored stored summary.",
  source: "fixture-source", category: "agents-applications",
  publishedAt: "2026-11-01T08:00:00Z", url: "https://publisher.test/article",
};
export const sourceCatalog: SourceCatalog = {
  sources: [{ id: "fixture-source", categories: ["agents-applications"] }],
  categories: [{ id: "agents-applications", label: "Agents and applications" },
    { id: "models", label: "Models" }],
};
export const newsDetail: NewsDetail = {
  ...newsItem, tags: ["ai"], author: "Authored publisher", dateOrigin: "published",
  publisherCategories: ["Authored category"],
};
export const page = (items: NewsItem[], nextCursor: string | null = null): NewsPage => ({
  items, nextCursor, readAt: "2026-11-01T08:00:00Z", cacheAgeSeconds: 0,
});
export const detail = async () => newsDetail;
export const briefingResponse: BriefingResponse = {
  briefing: {
    version: ["6f3a1499", "9b28", "4adc", "8269", "6d3b49ebdf8c"].join("-"),
    window_start: "2026-10-26T05:00:00Z", window_end: "2026-11-02T05:00:00Z",
    generated_at: "2026-11-02T05:10:00+00:00", coverage: "full", evidence_count: 21,
    tldr: { text: "Authored weekly overview <img src=x onerror=bad()>.", references: [1] },
    sections: Array.from({ length: 10 }, (_, index) => ({
      heading: `Authored weekly theme ${index + 1}`,
      paragraphs: [{
        text: `Authored briefing paragraph ${index + 1}. ` + Array.from({ length: 95 }, () => "reporting").join(" "),
        references: [1],
      }],
    })),
    citations: [{ number: 1, title: "Authored original <svg onload=bad()>", url: "https://publisher.test/briefing" }],
  },
  refresh: { expected_cutoff: "2026-11-02T05:00:00Z", state: "ready", stale: false },
  meta: { read_at: "2026-11-02T06:00:00+01:00", cache_age_seconds: 0, result_scope: "briefing" },
};
export const briefing = async (): Promise<BriefingResponse> => structuredClone(briefingResponse);
