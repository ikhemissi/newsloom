import { z } from "zod";
import { safeHttps } from "./config";
import type { BriefingResponse } from "./domain";
import { UiFailure } from "./domain";

const instant = z.iso.datetime({ offset: true });
const positive = z.number().int().positive();
const paragraph = z.strictObject({ text: z.string(), references: z.array(positive) });
const artifact = z.strictObject({
  version: z.uuid(), window_start: instant, window_end: instant, generated_at: instant,
  coverage: z.enum(["full", "limited", "empty"]), evidence_count: z.number().int().nonnegative(),
  tldr: paragraph.nullable(),
  sections: z.array(z.strictObject({ heading: z.string(), paragraphs: z.array(paragraph) })),
  citations: z.array(z.strictObject({
    number: positive, url: z.string().refine((value) => safeHttps(value) !== null), title: z.string(),
  })),
}).refine((value) => {
  const end = new Date(value.window_end);
  if (end.getUTCHours() !== 5 || end.getUTCMinutes() !== 0 || end.getUTCSeconds() !== 0
      || end.getUTCMilliseconds() !== 0
      || end.getTime() - Date.parse(value.window_start) !== 7 * 86400_000
      || Date.parse(value.generated_at) < end.getTime()) return false;
  if (value.coverage === "empty")
    return value.evidence_count === 0 && value.tldr === null
      && !value.sections.length && !value.citations.length;
  if (!value.evidence_count || !value.tldr?.text.trim() || !value.sections.length
      || !value.citations.length || /\r|\n/.test(value.tldr.text)) return false;
  const paragraphs = value.sections.flatMap((section) => section.paragraphs);
  if (value.sections.some((section) => !section.heading.trim() || !section.paragraphs.length)
      || paragraphs.some((part) => !part.text.trim())) return false;
  const words = paragraphs.map((part) => part.text).join(" ").trim().split(/\s+/u).length;
  return words <= 1100 && (value.coverage !== "full" || words >= 900)
    && value.citations.every((citation, index) => citation.number === index + 1)
    && [...paragraphs, value.tldr].every((part) =>
      part.references.every((number) => number <= value.citations.length));
});
const response = z.strictObject({
  briefing: artifact.nullable(),
  refresh: z.strictObject({
    expected_cutoff: instant, state: z.enum(["pending", "running", "ready", "failed"]), stale: z.boolean(),
  }),
  meta: z.strictObject({
    read_at: instant, cache_age_seconds: z.number().finite().nonnegative(), result_scope: z.literal("briefing"),
  }),
}).refine((value) => {
  const end = value.briefing ? Date.parse(value.briefing.window_end) : null;
  const cutoff = Date.parse(value.refresh.expected_cutoff);
  return (end === null || cutoff >= end)
    && value.refresh.stale === (end === null || end < cutoff);
});

export function parseBriefing(value: unknown): BriefingResponse {
  const result = response.safeParse(value);
  if (!result.success) throw new UiFailure("invalid_response");
  return result.data;
}
