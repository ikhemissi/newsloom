export type Failure = "configuration" | "authorization" | "interaction" | "invalid_input"
  | "invalid_response" | "invalid_search" | "invalid_filters" | "invalid_news_request" | "overloaded" | "timeout" | "unavailable" | "read_only" | "stopped" | "cancelled";

export class UiFailure extends Error {
  constructor(readonly category: Failure) { super(category); }
}

export const messages: Record<Failure, string> = {
  configuration: "The browser configuration is unavailable or invalid.",
  authorization: "Access was denied. Sign in with an authorized account.",
  interaction: "Sign-in is required. Your question will not be resent automatically.",
  invalid_input: "Enter a nonblank question of at most 8192 UTF-8 bytes.",
  invalid_response: "The service returned an invalid or incomplete response.",
  invalid_search: "Enter a search query of at most 2048 characters.",
  invalid_filters: "Choose available source/category IDs and valid, complete dates with the start no later than the end.",
  invalid_news_request: "The news request could not be accepted. Refresh or revise the filters before trying again.",
  overloaded: "The service is busy. Try again when you are ready.",
  timeout: "The request timed out. No completed result was received.",
  unavailable: "The service is unavailable. No request will be replayed automatically.",
  read_only: "Not available while Newsloom is read-only overnight.",
  stopped: "Stopped displaying this request. Server cancellation is not yet confirmed.",
  cancelled: "The agent confirmed cancellation.",
};

export function failureMessage(error: unknown): string {
  return messages[error instanceof UiFailure ? error.category : "unavailable"];
}

export type Phase = "retrieving" | "planning" | "synthesizing" | "validating";
export type Citation = { number: number; url: string; href: string | null; host: string | null };
export type Paragraph = { text: string; references: number[] };
export type Answer = { paragraphs: Paragraph[]; citations: Citation[] };
export type ResearchEvent = { kind: "progress"; phase: Phase }
  | { kind: "answer"; answer: Answer };

export interface ResearchClient {
  ask(question: string, signal: AbortSignal, itemIds?: readonly string[], filters?: NewsFilters): AsyncIterable<ResearchEvent>;
  stop(): Promise<boolean>;
}

export interface AuthSession {
  signedIn(): boolean;
  signIn(resource?: "news" | "agent"): Promise<void>;
  signOut(): Promise<void>;
  token(resource?: "news" | "agent"): Promise<string>;
}

export type NewsItem = {
  id: string; title: string; summary: string; source: string; category: string;
  publishedAt: string; url: string;
};

export type NewsFilters = Readonly<{ source?: string; category?: string; from?: string; to?: string }>;
export type SourceCatalog = {
  sources: { id: string; categories: string[] }[];
  categories: { id: string; label: string }[];
};
export type NewsPage = {
  items: NewsItem[]; nextCursor: string | null;
  readAt: string; cacheAgeSeconds: number;
};
export type Announcement = {
  statement: string; status: string; effectiveDate: string | null; deadline: string | null;
  products: string[];
};
export type NewsDetail = NewsItem & {
  tags: string[]; author: string; dateOrigin: "published" | "updated" | "retrieved";
  publisherCategories: string[]; announcements?: Announcement[];
};

export type BriefingParagraph = { text: string; references: number[] };
export type Briefing = {
  version: string; window_start: string; window_end: string; generated_at: string;
  coverage: "full" | "limited" | "empty" | "no_material_changes"; evidence_count: number;
  editorial_policy?: "architect-v1" | null | undefined;
  tldr: BriefingParagraph | null;
  sections: { heading: string; paragraphs: BriefingParagraph[] }[];
  citations: { number: number; url: string; title: string }[];
};
export type BriefingResponse = {
  briefing: Briefing | null;
  refresh: { expected_cutoff: string; state: "pending" | "running" | "ready" | "failed"; stale: boolean };
  meta: { read_at: string; cache_age_seconds: number; result_scope: "briefing" };
};

export interface NewsCatalog {
  briefing(signal: AbortSignal): Promise<BriefingResponse>;
  recent(signal: AbortSignal): Promise<NewsPage>;
  search(query: string | undefined, signal: AbortSignal, filters?: NewsFilters, cursor?: string): Promise<NewsPage>;
  sources(signal: AbortSignal): Promise<SourceCatalog>;
  detail(id: string, signal: AbortSignal): Promise<NewsDetail | null>;
}

export async function accessToken(
  auth: AuthSession, resource: "news" | "agent", signal: AbortSignal,
): Promise<string> {
  if (signal.aborted) throw new UiFailure("timeout");
  let abort: () => void = () => undefined;
  const interrupted = new Promise<string>((_, reject) => {
    abort = () => reject(new UiFailure("timeout"));
    signal.addEventListener("abort", abort, { once: true });
  });
  try { return await Promise.race([auth.token(resource), interrupted]); }
  finally { signal.removeEventListener("abort", abort); }
}
