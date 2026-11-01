import { Client, StreamableHTTPClientTransport } from "@modelcontextprotocol/client";
import { z } from "zod";
import type { RuntimeConfig } from "./config";
import type { AuthSession, NewsCatalog, NewsFilters, NewsItem, SourceCatalog } from "./domain";
import { accessToken, UiFailure } from "./domain";
import { guardedFetch } from "./research";
import { matchesFilters, newsIdSchema, validateFilters } from "./filters";

const itemSchema = z.object({
  id: z.uuid().transform((value) => value.toLowerCase()), title: z.string(), summary: z.string(),
  source: newsIdSchema,
  category: z.string().min(1), tags: z.array(z.string()),
  published_at: z.iso.datetime({ offset: true }), url: z.string(),
});
const resultSchema = z.object({ items: z.array(itemSchema).max(20) })
  .refine((value) => new Set(value.items.map((item) => item.id)).size === value.items.length);
const sourcesSchema = z.object({
  sources: z.array(z.object({ id: newsIdSchema, categories: z.array(newsIdSchema) })),
  categories: z.array(z.object({ id: newsIdSchema, label: z.string().min(1) })),
}).refine((value) => {
  const categories = new Set(value.categories.map((category) => category.id));
  return categories.size === value.categories.length
    && new Set(value.sources.map((source) => source.id)).size === value.sources.length
    && value.sources.every((source) => new Set(source.categories).size === source.categories.length
      && source.categories.every((category) => categories.has(category)));
});

export function validateSearch(value: string): string {
  const query = value.trim();
  if (!query || [...query].length > 2048
      || /[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/.test(query))
    throw new UiFailure("invalid_search");
  return query;
}

export class McpCatalog implements NewsCatalog {
  private active = new Set<"news" | "catalogue">();
  constructor(private config: RuntimeConfig, private auth: AuthSession, private fetchImpl: typeof fetch = fetch) {}
  recent(signal: AbortSignal): Promise<NewsItem[]> { return this.news("get_recent_news", { limit: 20 }, signal, {}); }
  search(value: string | undefined, signal: AbortSignal, filters: NewsFilters = {}): Promise<NewsItem[]> {
    const snapshot = validateFilters(filters);
    return this.news("search_news", {
      ...snapshot, ...(value === undefined ? {} : { query: validateSearch(value) }), limit: 20,
    }, signal, snapshot);
  }
  sources(signal: AbortSignal): Promise<SourceCatalog> {
    return this.load("list_sources", {}, signal, sourcesSchema);
  }
  private async news(name: "get_recent_news" | "search_news", args: NewsFilters & { limit: number; query?: string }, signal: AbortSignal, filters: NewsFilters): Promise<NewsItem[]> {
    const result = await this.load(name, args, signal, resultSchema);
    const items = result.items.map((item) => ({
      id: item.id, title: item.title, summary: item.summary, source: item.source,
      category: item.category, publishedAt: item.published_at, url: item.url,
    }));
    if (!items.every((item) => matchesFilters(item, filters))) throw new UiFailure("invalid_response");
    return items;
  }
  private async load<T>(name: "get_recent_news" | "search_news" | "list_sources", args: NewsFilters & { limit?: number; query?: string }, signal: AbortSignal, schema: z.ZodType<T>): Promise<T> {
    const lane = name === "list_sources" ? "catalogue" : "news";
    if (this.active.has(lane)) throw new UiFailure("overloaded");
    this.active.add(lane);
    const controller = new AbortController();
    const abort = () => controller.abort();
    signal.addEventListener("abort", abort, { once: true });
    if (signal.aborted) abort();
    const timer = setTimeout(abort, 90000);
    let client: Client | null = null;
    // Discovery wraps fetch errors; retain our authorization/deadline categories.
    let transportFailure: UiFailure | null = null;
    try {
      const token = await accessToken(this.auth, "news", controller.signal);
      if (controller.signal.aborted) throw new UiFailure("timeout");
      client = new Client({ name: "newsloom-browser", version: "0.1.0" }, {
        versionNegotiation: { mode: { pin: "2026-07-28" }, probe: { timeoutMs: 10000, maxRetries: 0 } },
      });
      const bounded = guardedFetch(this.config.mcpUrl, token, controller.signal, this.fetchImpl);
      const transport = new StreamableHTTPClientTransport(new URL(this.config.mcpUrl), {
        fetch: async (input, init) => {
          try { return await bounded(String(input), init); }
          catch (error) {
            if (error instanceof UiFailure) transportFailure = error;
            throw error;
          }
        },
        requestInit: { redirect: "error", credentials: "omit", signal: controller.signal },
      });
      await client.connect(transport);
      if (client.getProtocolEra() !== "modern") throw new UiFailure("invalid_response");
      const response = await client.callTool({ name, arguments: args }, {
        signal: controller.signal, timeout: 90000,
      });
      if (response.isError) throw new UiFailure("unavailable");
      const result = schema.safeParse(response.structuredContent);
      if (!result.success) throw new UiFailure("invalid_response");
      if (controller.signal.aborted) throw new UiFailure("timeout");
      return result.data;
    } catch (error) {
      if (error instanceof UiFailure) throw error;
      if (transportFailure) throw transportFailure;
      throw new UiFailure(controller.signal.aborted ? "timeout" : "unavailable");
    } finally {
      clearTimeout(timer);
      signal.removeEventListener("abort", abort);
      controller.abort();
      try { await client?.close(); }
      finally { this.active.delete(lane); }
    }
  }
}
