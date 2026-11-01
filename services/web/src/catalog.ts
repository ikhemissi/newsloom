import { Client, StreamableHTTPClientTransport } from "@modelcontextprotocol/client";
import { z } from "zod";
import type { RuntimeConfig } from "./config";
import type { AuthSession, NewsCatalog, NewsItem } from "./domain";
import { accessToken, UiFailure } from "./domain";
import { guardedFetch } from "./research";

const itemSchema = z.object({
  id: z.uuid().transform((value) => value.toLowerCase()), title: z.string(), summary: z.string(),
  source: z.string().regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/).max(128),
  category: z.string().min(1), tags: z.array(z.string()),
  published_at: z.iso.datetime({ offset: true }), url: z.string(),
});
const resultSchema = z.object({ items: z.array(itemSchema).max(20) })
  .refine((value) => new Set(value.items.map((item) => item.id)).size === value.items.length);

export function validateSearch(value: string): string {
  const query = value.trim();
  if (!query || [...query].length > 2048
      || /[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/.test(query))
    throw new UiFailure("invalid_search");
  return query;
}

export class McpCatalog implements NewsCatalog {
  private active = false;
  constructor(private config: RuntimeConfig, private auth: AuthSession, private fetchImpl: typeof fetch = fetch) {}
  recent(signal: AbortSignal): Promise<NewsItem[]> { return this.load("get_recent_news", { limit: 20 }, signal); }
  search(value: string, signal: AbortSignal): Promise<NewsItem[]> {
    return this.load("search_news", { query: validateSearch(value), limit: 20 }, signal);
  }
  private async load(name: "get_recent_news" | "search_news", args: { limit: number; query?: string }, signal: AbortSignal): Promise<NewsItem[]> {
    if (this.active) throw new UiFailure("overloaded");
    this.active = true;
    const controller = new AbortController();
    const abort = () => controller.abort();
    signal.addEventListener("abort", abort, { once: true });
    if (signal.aborted) abort();
    const timer = setTimeout(abort, 90000);
    let client: Client | null = null;
    try {
      const token = await accessToken(this.auth, "news", controller.signal);
      if (controller.signal.aborted) throw new UiFailure("timeout");
      client = new Client({ name: "newsloom-browser", version: "0.1.0" }, {
        versionNegotiation: { mode: { pin: "2026-07-28" }, probe: { timeoutMs: 10000, maxRetries: 0 } },
      });
      const bounded = guardedFetch(this.config.mcpUrl, token, controller.signal, this.fetchImpl);
      const transport = new StreamableHTTPClientTransport(new URL(this.config.mcpUrl), {
        fetch: (input, init) => bounded(String(input), init),
        requestInit: { redirect: "error", credentials: "omit", signal: controller.signal },
      });
      await client.connect(transport);
      if (client.getProtocolEra() !== "modern") throw new UiFailure("invalid_response");
      const response = await client.callTool({ name, arguments: args }, {
        signal: controller.signal, timeout: 90000,
      });
      if (response.isError) throw new UiFailure("unavailable");
      const result = resultSchema.safeParse(response.structuredContent);
      if (!result.success) throw new UiFailure("invalid_response");
      if (controller.signal.aborted) throw new UiFailure("timeout");
      return result.data.items.map((item) => ({
        id: item.id, title: item.title, summary: item.summary, source: item.source,
        category: item.category, publishedAt: item.published_at, url: item.url,
      }));
    } catch (error) {
      if (error instanceof UiFailure) throw error;
      throw new UiFailure(controller.signal.aborted ? "timeout" : "unavailable");
    } finally {
      clearTimeout(timer);
      signal.removeEventListener("abort", abort);
      controller.abort();
      try { await client?.close(); }
      finally { this.active = false; }
    }
  }
}
