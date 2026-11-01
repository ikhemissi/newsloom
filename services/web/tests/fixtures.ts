import type { RuntimeConfig } from "../src/config";
import type { NewsItem } from "../src/domain";

export const runtimeConfig: RuntimeConfig = {
  tenantId: crypto.randomUUID(), clientId: crypto.randomUUID(),
  agentUrl: "https://agent.test/a2a", agentScope: `api://${crypto.randomUUID()}/news.agent`,
  mcpUrl: "https://mcp.test/mcp", mcpScope: `api://${crypto.randomUUID()}/news.read`,
};
export const newsItem: NewsItem = {
  id: crypto.randomUUID(), title: "Authored news headline", summary: "Authored stored summary.",
  source: "fixture-source", category: "agents",
  publishedAt: "2026-11-01T08:00:00Z", url: "https://publisher.test/article",
};
