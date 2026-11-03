import { z } from "zod";
import type { RuntimeConfig } from "./config";
import type { AuthSession, NewsCatalog, NewsDetail, NewsFilters, NewsItem, NewsPage, SourceCatalog } from "./domain";
import { accessToken, UiFailure } from "./domain";
import { guardedFetch } from "./research";
import { matchesFilters, newsIdSchema, validateFilters } from "./filters";
import { parseBriefing } from "./briefing";

const itemSchema = z.object({
  id: z.uuid().transform((value) => value.toLowerCase()), title: z.string(), summary: z.string(),
  source: newsIdSchema, category: newsIdSchema, tags: z.array(z.string()),
  published_at: z.iso.datetime({ offset: true }), url: z.string(),
});
const cursorSchema = z.string().min(1).max(2048).regex(/^[A-Za-z0-9_-]+$/);
const metaSchema = z.object({
  read_at: z.iso.datetime({ offset: true }), cache_age_seconds: z.number().finite().nonnegative(),
  result_scope: z.enum(["page", "bounded", "item", "catalogue"]),
});
const pageSchema = z.object({
  items: z.array(itemSchema.extend({ similarity: z.number().finite().nullable().optional() })).max(20),
  next_cursor: cursorSchema.nullable(), meta: metaSchema,
}).refine((value) => new Set(value.items.map((item) => item.id)).size === value.items.length);
const sourcesSchema = z.object({
  sources: z.array(z.object({ id: newsIdSchema, categories: z.array(newsIdSchema) })),
  categories: z.array(z.object({ id: newsIdSchema, label: z.string().min(1) })),
  meta: metaSchema,
}).refine((value) => {
  const categories = new Set(value.categories.map((category) => category.id));
  return value.meta.result_scope === "catalogue" && categories.size === value.categories.length
    && new Set(value.sources.map((source) => source.id)).size === value.sources.length
    && value.sources.every((source) => new Set(source.categories).size === source.categories.length
      && source.categories.every((category) => categories.has(category)));
});
const detailSchema = z.object({
  item: itemSchema.extend({
    author: z.string(), date_origin: z.enum(["published", "updated", "retrieved"]),
    publisher_categories: z.array(z.string()),
  }), meta: metaSchema,
});
const mapItem = (item: z.infer<typeof itemSchema>): NewsItem => ({
  id: item.id, title: item.title, summary: item.summary, source: item.source,
  category: item.category, publishedAt: item.published_at, url: item.url,
});

export function validateSearch(value: string): string {
  const query = value.trim();
  if (!query || [...query].length > 2048
      || /[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/.test(query))
    throw new UiFailure("invalid_search");
  return query;
}

export class HttpCatalog implements NewsCatalog {
  private active = new Map<"news" | "catalogue" | "detail" | "briefing", AbortController>();
  constructor(private config: RuntimeConfig, private auth: AuthSession, private fetchImpl: typeof fetch = fetch) {}
  recent(signal: AbortSignal): Promise<NewsPage> { return this.search(undefined, signal); }
  async briefing(signal: AbortSignal) {
    return parseBriefing(await this.load("briefing", "/briefing", signal));
  }
  async search(value: string | undefined, signal: AbortSignal, filters: NewsFilters = {}, cursor?: string): Promise<NewsPage> {
    const snapshot = validateFilters(filters);
    if (cursor !== undefined && (!cursorSchema.safeParse(cursor).success || value !== undefined)) throw new UiFailure("invalid_news_request");
    const query = value === undefined ? undefined : validateSearch(value);
    const params = new URLSearchParams({ limit: "20", ...snapshot, ...(cursor ? { cursor } : {}) });
    const data = await this.load("news", query === undefined ? `/news?${params}` : "/search", signal,
      query === undefined ? undefined : { query, ...snapshot, limit: 20 });
    const result = pageSchema.safeParse(data);
    if (!result.success || result.data.meta.result_scope !== (query === undefined ? "page" : "bounded")
        || (query !== undefined && (result.data.next_cursor !== null
          || result.data.items.some((item) => typeof item.similarity !== "number")))
        || (!result.data.items.length && result.data.next_cursor !== null)
        || (cursor !== undefined && result.data.next_cursor === cursor))
      throw new UiFailure("invalid_response");
    const items = result.data.items.map(mapItem);
    if (!items.every((item) => matchesFilters(item, snapshot))) throw new UiFailure("invalid_response");
    return {
      items, nextCursor: result.data.next_cursor,
      readAt: result.data.meta.read_at, cacheAgeSeconds: result.data.meta.cache_age_seconds,
    };
  }
  async sources(signal: AbortSignal): Promise<SourceCatalog> {
    const result = sourcesSchema.safeParse(await this.load("catalogue", "/sources", signal));
    if (!result.success) throw new UiFailure("invalid_response");
    return { sources: result.data.sources, categories: result.data.categories };
  }
  async detail(value: string, signal: AbortSignal): Promise<NewsDetail | null> {
    const id = z.uuid().safeParse(value);
    if (!id.success) throw new UiFailure("invalid_news_request");
    const data = await this.load("detail", `/news/${id.data.toLowerCase()}`, signal);
    if (data === null) return null;
    const result = detailSchema.safeParse(data);
    if (!result.success || result.data.item.id !== id.data.toLowerCase()
        || result.data.meta.result_scope !== "item") throw new UiFailure("invalid_response");
    const item = result.data.item;
    return { ...mapItem(item), tags: item.tags, author: item.author,
      dateOrigin: item.date_origin, publisherCategories: item.publisher_categories };
  }
  private async load(lane: "news" | "catalogue" | "detail" | "briefing", path: string, signal: AbortSignal, body?: object): Promise<unknown> {
    if (this.active.get(lane) && !this.active.get(lane)?.signal.aborted) throw new UiFailure("overloaded");
    const controller = new AbortController();
    this.active.set(lane, controller);
    const abort = () => controller.abort();
    signal.addEventListener("abort", abort, { once: true });
    if (signal.aborted) abort();
    const timer = setTimeout(abort, 90000);
    try {
      const token = await accessToken(this.auth, "news", controller.signal);
      if (controller.signal.aborted) throw new UiFailure("timeout");
      const endpoint = this.config.newsApiUrl + path;
      const bounded = guardedFetch(endpoint, token, controller.signal, this.fetchImpl, [400, 404, 413]);
      const response = await bounded(endpoint, {
        method: body ? "POST" : "GET", cache: "no-store",
        headers: { Accept: "application/json", ...(body ? { "Content-Type": "application/json" } : {}) },
        ...(body ? { body: JSON.stringify(body) } : {}),
      });
      if (!response.ok) {
        await response.body?.cancel();
        if (response.status === 404 && lane === "detail") return null;
        throw new UiFailure(response.status === 400 || response.status === 413 ? "invalid_news_request" : "unavailable");
      }
      if (!response.headers.get("content-type")?.toLowerCase().startsWith("application/json")) {
        await response.body?.cancel();
        throw new UiFailure("invalid_response");
      }
      const data: unknown = await response.json();
      if (controller.signal.aborted) throw new UiFailure("timeout");
      return data;
    } catch (error) {
      if (error instanceof UiFailure) throw error;
      throw new UiFailure(controller.signal.aborted ? "timeout" : "invalid_response");
    } finally {
      clearTimeout(timer);
      signal.removeEventListener("abort", abort);
      controller.abort();
      if (this.active.get(lane) === controller) this.active.delete(lane);
    }
  }
}
