import type { CardState, ProductDetail, Radar, RadarCard, RadarClient, RadarEntry, RadarProduct, StackEntry, Tier } from "../src/radar";

/** Shape written by scripts/triage_preview.py (`radar-fixture.json`). */
export type FixtureCard = {
  id: string; news_id: string; title: string; url: string; source: string; published_at: string;
  article_kind: string; statement: string; status: string; effective_date: string | null;
  deadline: string | null; products: { name: string; vendor: string }[];
  tier: Tier; reason: string; capability: string;
};

const DAY = 86_400_000;
const tiers: Tier[] = ["act_now", "worth_knowing", "later"];

/**
 * In-memory radar with the planned server rules: personalisation by stack, Done/Snooze,
 * cross-vendor grouping by capability and nearest-deadline ordering. Used by the local
 * mock-up and component tests; the server implements the same rules in SQL.
 */
export class FixtureRadar implements RadarClient {
  private cards: RadarCard[];
  private entities = new Map<string, StackEntry>();
  private stackIds = new Set<string>();
  private states = new Map<string, { state: CardState; until: number }>();
  calls: string[] = [];

  constructor(source: FixtureCard[], private now = () => new Date()) {
    const ids = new Map<string, string>();
    const id = (key: string) => ids.get(key) ?? (ids.set(key, crypto.randomUUID()), ids.get(key)!);
    this.cards = source.map((card) => {
      const products: RadarProduct[] = card.products.map((product) => {
        const vendorId = id(`vendor:${product.vendor}`);
        const productId = id(`product:${product.vendor}:${product.name.toLowerCase()}`);
        this.entities.set(vendorId, { id: vendorId, name: product.vendor, kind: "vendor", vendor: null });
        if (!this.entities.has(productId))
          this.entities.set(productId, { id: productId, name: product.name, kind: "product", vendor: product.vendor });
        return { id: productId, name: product.name, vendor: product.vendor, vendorId };
      });
      return {
        id: id(`card:${card.id}`), newsId: id(`news:${card.news_id}`), title: card.title, url: card.url,
        source: card.source, publishedAt: card.published_at, articleKind: card.article_kind,
        statement: card.statement, status: card.status, effectiveDate: card.effective_date,
        deadline: card.deadline, products, tier: card.tier, reason: card.reason,
        capability: card.capability, inStack: false, state: null,
      };
    });
  }

  async radar(window: 7 | 30): Promise<Radar> {
    this.calls.push(`radar:${window}`);
    const now = this.now().getTime();
    const visible: RadarCard[] = [];
    const hidden: RadarCard[] = [];
    for (const original of this.cards) {
      if (now - Date.parse(original.publishedAt) > window * DAY) continue;
      const saved = this.states.get(original.id);
      const state = saved && (saved.state === "done" || saved.until > now) ? saved.state : null;
      const inStack = original.products.some((product) =>
        this.stackIds.has(product.id) || this.stackIds.has(product.vendorId));
      const urgent = !this.stackIds.size || inStack || ["security", "regulation"].includes(original.articleKind);
      const tier: Tier = original.tier === "act_now" && !urgent ? "worth_knowing" : original.tier;
      const card = { ...original, tier, inStack, state };
      (state ? hidden : visible).push(card);
    }
    const order = (left: RadarCard, right: RadarCard) =>
      Number(right.inStack) - Number(left.inStack)
      || (left.deadline ?? "9999").localeCompare(right.deadline ?? "9999")
      || right.publishedAt.localeCompare(left.publishedAt);
    const result = Object.fromEntries(tiers.map((tier) => [tier, this.entries(
      visible.filter((card) => card.tier === tier).sort(order))])) as Record<Tier, RadarEntry[]>;
    const today = new Date(now).toISOString().slice(0, 10);
    const horizon = new Date(now + 90 * DAY).toISOString().slice(0, 10);
    return {
      window, tiers: result, hidden,
      deadlines: visible.filter((card) => card.tier !== "later" && card.deadline
        && card.deadline >= today && card.deadline <= horizon)
        .sort((left, right) => left.deadline!.localeCompare(right.deadline!)),
    };
  }

  private entries(cards: RadarCard[]): RadarEntry[] {
    const groups = new Map<string, RadarCard[]>();
    for (const card of cards) if (card.capability && card.capability !== "other")
      groups.set(card.capability, [...(groups.get(card.capability) ?? []), card]);
    const grouped = new Set<string>();
    const entries: RadarEntry[] = [];
    for (const card of cards) {
      const group = card.capability ? groups.get(card.capability) : undefined;
      const vendors = new Set(group?.flatMap((item) => item.products.map((product) => product.vendor)));
      if (group && group.length >= 2 && vendors.size >= 2) {
        if (grouped.has(card.capability!)) continue;
        grouped.add(card.capability!);
        entries.push({ kind: "group", capability: card.capability!, cards: group });
      } else entries.push({ kind: "card", card });
    }
    return entries;
  }

  async setCard(id: string, state: CardState | null): Promise<void> {
    this.calls.push(`card:${state ?? "active"}`);
    if (state) this.states.set(id, { state, until: this.now().getTime() + 7 * DAY });
    else this.states.delete(id);
  }

  async stack(): Promise<StackEntry[]> {
    return [...this.stackIds].flatMap((id) => this.entities.get(id) ?? []);
  }

  async setStack(ids: string[]): Promise<StackEntry[]> {
    this.calls.push(`stack:${ids.length}`);
    this.stackIds = new Set(ids.filter((id) => this.entities.has(id)).slice(0, 50));
    return this.stack();
  }

  async search(query: string): Promise<StackEntry[]> {
    const needle = query.toLowerCase();
    return [...this.entities.values()].filter((entry) => entry.name.toLowerCase().includes(needle))
      .sort((left, right) => Number(right.kind === "vendor") - Number(left.kind === "vendor") || left.name.localeCompare(right.name))
      .slice(0, 10);
  }

  async product(id: string): Promise<ProductDetail | null> {
    const entry = this.entities.get(id);
    if (!entry || entry.kind !== "product") return null;
    const timeline = this.cards.filter((card) => card.products.some((product) => product.id === id))
      .sort((left, right) => right.publishedAt.localeCompare(left.publishedAt));
    return { id, name: entry.name, vendor: entry.vendor ?? "", aliases: [], related: [], timeline };
  }
}
