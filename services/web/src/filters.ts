import { z } from "zod";
import type { NewsFilters, NewsItem, SourceCatalog } from "./domain";
import { UiFailure } from "./domain";

export const newsIdSchema = z.string().regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/).max(128);
const timestampSchema = z.iso.datetime({ offset: true }).refine((value) => {
  const year = new Date(value).getUTCFullYear();
  return year >= 1 && year <= 9999;
});
const filtersSchema = z.object({
  source: newsIdSchema.optional(), category: newsIdSchema.optional(),
  from: timestampSchema.optional(), to: timestampSchema.optional(),
}).strict().refine((value) => !value.from || !value.to || Date.parse(value.from) < Date.parse(value.to));

export type DatePeriod = "any" | "today" | "7days" | "30days" | "custom";
export type FilterDraft = { source: string; category: string; period: DatePeriod; start: string; end: string };
export type FilterSnapshot = Readonly<{ filters: NewsFilters; labels: readonly string[] }>;
export const emptyDraft: FilterDraft = { source: "", category: "", period: "any", start: "", end: "" };
export const emptySnapshot: FilterSnapshot = Object.freeze({
  filters: Object.freeze({}), labels: Object.freeze(["Any source", "Any category", "Any time"]),
});

export function validateFilters(value: NewsFilters): NewsFilters {
  const result = filtersSchema.safeParse(value);
  if (!result.success) throw new UiFailure("invalid_filters");
  const { source, category, from, to } = result.data;
  return Object.freeze({
    ...(source === undefined ? {} : { source }), ...(category === undefined ? {} : { category }),
    ...(from === undefined ? {} : { from }), ...(to === undefined ? {} : { to }),
  });
}

function localDay(year: number, month: number, day: number): Date {
  const value = new Date(0);
  value.setHours(0, 0, 0, 0);
  value.setFullYear(year, month, day);
  return value;
}

function parseDay(text: string): Date {
  const parts = /^(\d{4})-(\d{2})-(\d{2})$/.exec(text);
  if (!parts) throw new UiFailure("invalid_filters");
  const year = Number(parts[1]), month = Number(parts[2]) - 1, day = Number(parts[3]);
  const value = localDay(year, month, day);
  if (year < 1 || value.getFullYear() !== year || value.getMonth() !== month || value.getDate() !== day)
    throw new UiFailure("invalid_filters");
  return value;
}

function shiftDay(value: Date, days: number): Date {
  return localDay(value.getFullYear(), value.getMonth(), value.getDate() + days);
}

function dayLabel(value: Date): string {
  return `${String(value.getFullYear()).padStart(4, "0")}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
}

export function buildFilters(draft: FilterDraft, catalogue: SourceCatalog | null, now = new Date()): FilterSnapshot {
  const source = draft.source ? catalogue?.sources.find((value) => value.id === draft.source) : undefined;
  const category = draft.category ? catalogue?.categories.find((value) => value.id === draft.category) : undefined;
  if ((draft.source && !source) || (draft.category && !category)) throw new UiFailure("invalid_filters");
  const metadata = { ...(source ? { source: source.id } : {}), ...(category ? { category: category.id } : {}) };
  const labels = [source ? `Source: ${source.id}` : "Any source", category ? `Category: ${category.label}` : "Any category"];
  if (draft.period === "any") return Object.freeze({
    filters: validateFilters(metadata), labels: Object.freeze([...labels, "Any time"]),
  });
  const today = localDay(now.getFullYear(), now.getMonth(), now.getDate());
  const start = draft.period === "custom" ? parseDay(draft.start)
    : shiftDay(today, draft.period === "7days" ? -6 : draft.period === "30days" ? -29 : 0);
  const end = draft.period === "custom" ? parseDay(draft.end) : today;
  if (start > end) throw new UiFailure("invalid_filters");
  const names = { today: "Today", "7days": "Last 7 days", "30days": "Last 30 days", custom: "Custom dates" };
  return Object.freeze({
    filters: validateFilters({ ...metadata, from: start.toISOString(), to: shiftDay(end, 1).toISOString() }),
    labels: Object.freeze([...labels, `${names[draft.period]}: ${dayLabel(start)} to ${dayLabel(end)} (local dates)`]),
  });
}

export function matchesFilters(item: NewsItem, filters: NewsFilters): boolean {
  const published = Date.parse(item.publishedAt);
  return (!filters.source || item.source === filters.source)
    && (!filters.category || item.category === filters.category)
    && (!filters.from || published >= Date.parse(filters.from))
    && (!filters.to || published < Date.parse(filters.to));
}
