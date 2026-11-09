import { z } from "zod";
import type { RuntimeConfig } from "./config";
import type { AuthSession } from "./domain";
import { accessToken, UiFailure } from "./domain";
import { guardedFetch } from "./research";
import type { CardState, ProductDetail, Radar, RadarCard, RadarClient, RadarEntry, StackEntry, Tier } from "./radar";

const tier = z.enum(["act_now", "worth_knowing", "later"]);
const day = z.iso.date().nullable();
const product = z.strictObject({ id: z.uuid(), name: z.string().min(1), vendor: z.string().min(1), vendor_id: z.uuid() });
const card = z.strictObject({
  id: z.uuid(), news_id: z.uuid(), title: z.string(), url: z.string(), source: z.string(),
  published_at: z.iso.datetime({ offset: true }), article_kind: z.string(), statement: z.string().min(1),
  status: z.string(), effective_date: day, deadline: day, products: z.array(product).max(5), tier,
  reason: z.string().nullable(), capability: z.string().nullable(), in_stack: z.boolean(),
  state: z.enum(["done", "snoozed"]).nullable(),
});
const entry = z.discriminatedUnion("kind", [
  z.strictObject({ kind: z.literal("card"), card }),
  z.strictObject({ kind: z.literal("group"), capability: z.string().min(1), cards: z.array(card).min(2) }),
]);
const radarSchema = z.strictObject({
  window: z.union([z.literal(7), z.literal(30)]),
  tiers: z.strictObject({ act_now: z.array(entry), worth_knowing: z.array(entry), later: z.array(entry) }),
  deadlines: z.array(card), hidden: z.array(card),
});
const stackEntry = z.strictObject({
  id: z.uuid(), name: z.string().min(1), kind: z.enum(["vendor", "product"]), vendor: z.string().nullable(),
});
const entries = z.strictObject({ items: z.array(stackEntry).max(50) });
const productSchema = z.strictObject({
  id: z.uuid(), name: z.string().min(1), vendor: z.string().min(1), aliases: z.array(z.string()),
  related: z.array(z.strictObject({ id: z.uuid(), name: z.string(), relation: z.enum(["part_of", "replaces"]) })),
  timeline: z.array(card).max(100),
});

function parsed<T>(schema: z.ZodType<T>, data: unknown): T {
  const result = schema.safeParse(data);
  if (!result.success) throw new UiFailure("invalid_response");
  return result.data;
}
function identifier(value: string): string {
  if (!z.uuid().safeParse(value).success) throw new UiFailure("invalid_news_request");
  return value.toLowerCase();
}

type WireCard = z.infer<typeof card>;
function mapCard(value: WireCard): RadarCard {
  return {
    id: value.id, newsId: value.news_id, title: value.title, url: value.url, source: value.source,
    publishedAt: value.published_at, articleKind: value.article_kind, statement: value.statement,
    status: value.status, effectiveDate: value.effective_date, deadline: value.deadline,
    products: value.products.map((item) => ({ id: item.id, name: item.name, vendor: item.vendor, vendorId: item.vendor_id })),
    tier: value.tier, reason: value.reason, capability: value.capability, inStack: value.in_stack, state: value.state,
  };
}
function mapEntry(value: z.infer<typeof entry>): RadarEntry {
  return value.kind === "card" ? { kind: "card", card: mapCard(value.card) }
    : { kind: "group", capability: value.capability, cards: value.cards.map(mapCard) };
}

/** Radar reads and per-reader writes; single-flight per lane, never cached by the browser. */
export class HttpRadar implements RadarClient {
  private active = new Map<string, AbortController>();
  constructor(private config: RuntimeConfig, private auth: AuthSession, private fetchImpl: typeof fetch = fetch) {}

  async radar(window: 7 | 30, signal: AbortSignal): Promise<Radar> {
    const data = parsed(radarSchema, await this.request("radar", `/radar?window=${window}`, signal));
    return {
      window: data.window, deadlines: data.deadlines.map(mapCard), hidden: data.hidden.map(mapCard),
      tiers: Object.fromEntries((Object.keys(data.tiers) as Tier[]).map((name) =>
        [name, data.tiers[name].map(mapEntry)])) as Record<Tier, RadarEntry[]>,
    };
  }
  async setCard(id: string, state: CardState | null, signal: AbortSignal): Promise<void> {
    const card = identifier(id);
    await this.request(`card:${card}`, `/me/cards/${card}`, signal, { state });
  }
  async stack(signal: AbortSignal): Promise<StackEntry[]> {
    return parsed(entries, await this.request("stack", "/me/stack", signal)).items;
  }
  async setStack(ids: string[], signal: AbortSignal): Promise<StackEntry[]> {
    return parsed(entries, await this.request("stack-update", "/me/stack", signal, { ids })).items;
  }
  async search(query: string, signal: AbortSignal): Promise<StackEntry[]> {
    const params = new URLSearchParams({ query: query.slice(0, 100) });
    return parsed(entries, await this.request("search", `/products?${params}`, signal)).items;
  }
  async product(id: string, signal: AbortSignal): Promise<ProductDetail | null> {
    const data = await this.request("product", `/products/${identifier(id)}`, signal, undefined, true);
    if (data === null) return null;
    const value = parsed(productSchema, data);
    return { ...value, timeline: value.timeline.map(mapCard) };
  }

  private async request(lane: string, path: string, signal: AbortSignal, body?: object, missing = false): Promise<unknown> {
    if (this.active.get(lane) && !this.active.get(lane)?.signal.aborted) throw new UiFailure("overloaded");
    const controller = new AbortController();
    this.active.set(lane, controller);
    const abort = () => controller.abort();
    signal.addEventListener("abort", abort, { once: true });
    if (signal.aborted) abort();
    const timer = setTimeout(abort, 30000);
    try {
      const token = await accessToken(this.auth, "news", controller.signal);
      const endpoint = this.config.newsApiUrl + path;
      const response = await guardedFetch(endpoint, token, controller.signal, this.fetchImpl, [400, 404])(endpoint, {
        method: body ? "PUT" : "GET", cache: "no-store",
        headers: { Accept: "application/json", ...(body ? { "Content-Type": "application/json" } : {}) },
        ...(body ? { body: JSON.stringify(body) } : {}),
      });
      if (response.status === 404 && missing) { await response.body?.cancel(); return null; }
      if (response.status === 400 || response.status === 404) {
        await response.body?.cancel();
        throw new UiFailure("invalid_news_request");
      }
      if (!response.headers.get("content-type")?.toLowerCase().startsWith("application/json"))
        throw new UiFailure("invalid_response");
      return await response.json();
    } catch (error) {
      if (error instanceof UiFailure) throw error;
      throw new UiFailure(controller.signal.aborted ? "timeout" : "invalid_response");
    } finally {
      clearTimeout(timer);
      signal.removeEventListener("abort", abort);
      if (this.active.get(lane) === controller) this.active.delete(lane);
    }
  }
}
