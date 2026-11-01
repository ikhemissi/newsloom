// @vitest-environment node
import { afterEach, expect, test } from "vitest";
import { buildFilters, emptyDraft, matchesFilters, validateFilters } from "../src/filters";
import { newsItem, sourceCatalog } from "./fixtures";

const originalTimezone = process.env.TZ;
afterEach(() => {
  if (originalTimezone === undefined) delete process.env.TZ;
  else process.env.TZ = originalTimezone;
});

test("Any time omits both bounds and metadata uses exact catalogue IDs, not labels", () => {
  const snapshot = buildFilters({ ...emptyDraft, source: "fixture-source", category: "agents-applications" }, sourceCatalog);
  expect(snapshot.filters).toEqual({ source: "fixture-source", category: "agents-applications" });
  expect(snapshot.labels).toContain("Category: Agents and applications");
  expect(() => buildFilters({ ...emptyDraft, category: "Agents and applications" }, sourceCatalog)).toThrow("invalid_filters");
  expect(() => buildFilters({ ...emptyDraft, source: "unknown" }, sourceCatalog)).toThrow("invalid_filters");
  expect(buildFilters(emptyDraft, null).filters).toEqual({});
  expect(Object.isFrozen(snapshot.filters)).toBe(true);
});

test("Today and 7/30-day periods count local calendar days, not fixed hours", () => {
  process.env.TZ = "America/New_York";
  const now = new Date("2026-03-08T16:00:00Z");
  const today = buildFilters({ ...emptyDraft, period: "today" }, null, now);
  expect(today.filters).toEqual({ from: "2026-03-08T05:00:00.000Z", to: "2026-03-09T04:00:00.000Z" });
  expect(buildFilters({ ...emptyDraft, period: "7days" }, null, now).filters).toEqual({
    from: "2026-03-02T05:00:00.000Z", to: "2026-03-09T04:00:00.000Z",
  });
  expect(buildFilters({ ...emptyDraft, period: "30days" }, null, now).filters).toEqual({
    from: "2026-02-07T05:00:00.000Z", to: "2026-03-09T04:00:00.000Z",
  });
  const autumn = buildFilters({ ...emptyDraft, period: "today" }, null, new Date("2026-11-01T16:00:00Z"));
  expect(autumn.filters).toEqual({ from: "2026-11-01T04:00:00.000Z", to: "2026-11-02T05:00:00.000Z" });
});

test("custom dates include leap day and map offset-equivalent lower/exclusive upper boundaries", () => {
  process.env.TZ = "Asia/Tokyo";
  const { filters } = buildFilters({ ...emptyDraft, period: "custom", start: "2024-02-29", end: "2024-02-29" }, null);
  expect(filters).toEqual({ from: "2024-02-28T15:00:00.000Z", to: "2024-02-29T15:00:00.000Z" });
  expect(matchesFilters({ ...newsItem, publishedAt: "2024-02-29T00:00:00+09:00" }, filters)).toBe(true);
  expect(matchesFilters({ ...newsItem, publishedAt: "2024-02-28T14:59:59.999Z" }, filters)).toBe(false);
  expect(matchesFilters({ ...newsItem, publishedAt: "2024-03-01T00:00:00+09:00" }, filters)).toBe(false);
  expect(matchesFilters({ ...newsItem, publishedAt: "2024-02-29T14:59:59.999Z" }, filters)).toBe(true);
});

test("missing, malformed, impossible, reversed and unsupported wire intervals fail", () => {
  process.env.TZ = "UTC";
  const invalidRanges: [string, string][] = [
    ["", ""], ["2026-01-01", ""], ["", "2026-01-01"],
    ["2026-02-29", "2026-03-01"], ["2026-04-31", "2026-05-01"],
    ["2026-02-02", "2026-02-01"], ["2026-13-01", "2026-13-02"],
    ["26-01-01", "26-01-02"], ["0000-01-01", "0000-01-02"],
    ["9999-12-31", "9999-12-31"],
  ];
  for (const [start, end] of invalidRanges)
    expect(() => buildFilters({ ...emptyDraft, period: "custom", start, end }, null)).toThrow("invalid_filters");
  expect(() => validateFilters({ from: "2026-01-01", to: "2026-02-01" })).toThrow("invalid_filters");
  expect(() => validateFilters({ from: "0001-01-01T00:00:00+09:00" })).toThrow("invalid_filters");
  expect(() => validateFilters({ to: "9999-12-31T23:00:00-09:00" })).toThrow("invalid_filters");
  expect(() => validateFilters({ from: "2026-02-01T00:00:00Z", to: "2026-02-01T00:00:00Z" })).toThrow("invalid_filters");
});
