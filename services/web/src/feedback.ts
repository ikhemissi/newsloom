import { z } from "zod";
import type { RuntimeConfig } from "./config";
import type { AuthSession } from "./domain";
import { accessToken, UiFailure } from "./domain";
import { guardedFetch } from "./research";

export const MAX_COMMENT = 1000;
export type Rating = "up" | "down";
export type FeedbackTarget = { type: "briefing" | "research"; ref: string };
export type ResearchSnapshot = {
  question: string; answer: Record<string, unknown>;
  citations: Record<string, unknown>[]; filters: Record<string, unknown>;
};
export type FeedbackEntry = {
  target: FeedbackTarget; rating: Rating; comment: string | null; snapshot?: ResearchSnapshot;
};
export type Vote = { rating: Rating; comment: string | null };
export type ReviewQuery = { rating?: Rating | undefined; targetType?: FeedbackTarget["type"] | undefined; days: number };
export type ReviewItem = {
  created_at: string; target_type: FeedbackTarget["type"]; target_ref: string; rating: Rating;
  comment: string | null; snapshot: Record<string, unknown> | null;
};

export interface FeedbackClient {
  submit(entry: FeedbackEntry, signal: AbortSignal): Promise<void>;
  mine(target: FeedbackTarget, signal: AbortSignal): Promise<Vote | null>;
  review(query: ReviewQuery, signal: AbortSignal): Promise<ReviewItem[]>;
  exportLines(query: ReviewQuery, signal: AbortSignal): Promise<string>;
}

const rating = z.enum(["up", "down"]);
const vote = z.strictObject({ rating, comment: z.string().max(MAX_COMMENT).nullable() });
const mineSchema = z.strictObject({ vote: vote.nullable() });
const item = z.strictObject({
  created_at: z.iso.datetime({ offset: true }), target_type: z.enum(["briefing", "research"]),
  target_ref: z.string().min(1).max(200), rating, comment: z.string().max(MAX_COMMENT).nullable(),
  snapshot: z.record(z.string(), z.unknown()).nullable(),
});
const reviewSchema = z.strictObject({ items: z.array(item).max(1000) });

export function validateComment(value: string): string | null {
  const comment = value.trim();
  if ([...comment].length > MAX_COMMENT) throw new UiFailure("invalid_input");
  return comment || null;
}

function reviewParams(query: ReviewQuery): string {
  const params = new URLSearchParams({ days: String(query.days), limit: "200" });
  if (query.rating) params.set("rating", query.rating);
  if (query.targetType) params.set("target_type", query.targetType);
  return params.toString();
}

/** Feedback has its own single-flight lanes so it never blocks or aborts news reads. */
export class HttpFeedback implements FeedbackClient {
  private active = new Map<string, AbortController>();
  constructor(private config: RuntimeConfig, private auth: AuthSession, private fetchImpl: typeof fetch = fetch) {}

  async submit(entry: FeedbackEntry, signal: AbortSignal): Promise<void> {
    await this.request("submit", "/feedback", signal, {
      target_type: entry.target.type, target_ref: entry.target.ref, rating: entry.rating,
      comment: entry.comment, ...(entry.snapshot ? { snapshot: entry.snapshot } : {}),
    });
  }
  async mine(target: FeedbackTarget, signal: AbortSignal): Promise<Vote | null> {
    const params = new URLSearchParams({ target_type: target.type, target_ref: target.ref });
    const result = mineSchema.safeParse(await this.json(`mine:${target.type}:${target.ref}`,
      `/feedback/mine?${params}`, signal));
    if (!result.success) throw new UiFailure("invalid_response");
    return result.data.vote;
  }
  async review(query: ReviewQuery, signal: AbortSignal): Promise<ReviewItem[]> {
    const result = reviewSchema.safeParse(await this.json("review", `/feedback/review?${reviewParams(query)}`, signal));
    if (!result.success) throw new UiFailure("invalid_response");
    return result.data.items;
  }
  async exportLines(query: ReviewQuery, signal: AbortSignal): Promise<string> {
    const response = await this.request("export", `/feedback/export?${reviewParams(query)}`, signal);
    if (!response.headers.get("content-type")?.toLowerCase().startsWith("application/x-ndjson"))
      throw new UiFailure("invalid_response");
    return response.text();
  }

  private async json(lane: string, path: string, signal: AbortSignal): Promise<unknown> {
    const response = await this.request(lane, path, signal);
    if (!response.headers.get("content-type")?.toLowerCase().startsWith("application/json"))
      throw new UiFailure("invalid_response");
    return response.json();
  }
  private async request(lane: string, path: string, signal: AbortSignal, body?: object): Promise<Response> {
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
      const response = await guardedFetch(endpoint, token, controller.signal, this.fetchImpl, [400, 413])(endpoint, {
        method: body ? "POST" : "GET", cache: "no-store",
        headers: { Accept: "application/json, application/x-ndjson",
          ...(body ? { "Content-Type": "application/json" } : {}) },
        ...(body ? { body: JSON.stringify(body) } : {}),
      });
      if (response.status === 400 || response.status === 413) {
        await response.body?.cancel();
        throw new UiFailure("invalid_input");
      }
      return response;
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
