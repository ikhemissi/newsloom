import type { RuntimeConfig } from "../src/config";
import type { NewsItem, SourceCatalog } from "../src/domain";

export const runtimeConfig: RuntimeConfig = {
  tenantId: crypto.randomUUID(), clientId: crypto.randomUUID(),
  agentUrl: "https://agent.test/a2a", agentScope: `api://${crypto.randomUUID()}/news.agent`,
  mcpUrl: "https://mcp.test/mcp", mcpScope: `api://${crypto.randomUUID()}/news.read`,
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
