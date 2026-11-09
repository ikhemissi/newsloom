export type Tier = "act_now" | "worth_knowing" | "later";
export type CardState = "done" | "snoozed";

export type RadarProduct = { id: string; name: string; vendor: string; vendorId: string };
export type RadarCard = {
  id: string; newsId: string; title: string; url: string; source: string; publishedAt: string;
  articleKind: string; statement: string; status: string;
  effectiveDate: string | null; deadline: string | null;
  products: RadarProduct[]; tier: Tier; reason: string | null; capability: string | null;
  inStack: boolean; state: CardState | null;
};
export type RadarEntry = { kind: "card"; card: RadarCard }
  | { kind: "group"; capability: string; cards: RadarCard[] };
export type Radar = {
  window: 7 | 30;
  tiers: Record<Tier, RadarEntry[]>;
  deadlines: RadarCard[];
  hidden: RadarCard[];
};
export type StackEntry = { id: string; name: string; kind: "vendor" | "product"; vendor: string | null };
export type ProductDetail = {
  id: string; name: string; vendor: string; aliases: string[];
  related: { id: string; name: string; relation: string }[];
  timeline: RadarCard[];
};

export interface RadarClient {
  radar(window: 7 | 30, signal: AbortSignal): Promise<Radar>;
  setCard(id: string, state: CardState | null, signal: AbortSignal): Promise<void>;
  stack(signal: AbortSignal): Promise<StackEntry[]>;
  setStack(ids: string[], signal: AbortSignal): Promise<StackEntry[]>;
  search(query: string, signal: AbortSignal): Promise<StackEntry[]>;
  product(id: string, signal: AbortSignal): Promise<ProductDetail | null>;
}

export const tierLabels: Record<Tier, string> = {
  act_now: "Act now", worth_knowing: "Worth knowing", later: "When you have time",
};
export const statusLabels: Record<string, string> = {
  announced: "Announced", preview: "Preview", ga: "GA", updated: "Updated",
  deprecated: "Deprecated", retired: "Retired",
};

export function entryCards(entry: RadarEntry): RadarCard[] {
  return entry.kind === "card" ? [entry.card] : entry.cards;
}

export function daysUntil(date: string, now: Date): number {
  return Math.ceil((Date.parse(`${date}T00:00:00Z`) - now.getTime()) / 86_400_000);
}
