import type { RuntimeConfig } from "../src/config";
import type { NewsDetail, NewsItem, NewsPage, SourceCatalog } from "../src/domain";

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
