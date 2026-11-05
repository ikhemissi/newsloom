import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { App } from "../src/App";
import { BriefingPanel } from "../src/BriefingPanel";
import { FeedbackControls, ReviewPage } from "../src/Feedback";
import { parseAnswer } from "../src/answer";
import type { AuthSession, ResearchClient } from "../src/domain";
import { UiFailure } from "../src/domain";
import type { FeedbackClient, FeedbackEntry, ReviewItem } from "../src/feedback";
import { HttpFeedback, MAX_COMMENT } from "../src/feedback";
import { briefing, briefingResponse, detail, newsItem, page, runtimeConfig, sourceCatalog } from "./fixtures";

vi.stubGlobal("matchMedia", () => ({ matches: false }));

function client(overrides: Partial<FeedbackClient> = {}): FeedbackClient & { sent: FeedbackEntry[] } {
  const sent: FeedbackEntry[] = [];
  return {
    sent,
    submit: vi.fn(async (entry: FeedbackEntry) => { sent.push(entry); }),
    mine: vi.fn(async () => null),
    review: vi.fn(async () => []),
    exportLines: vi.fn(async () => ""),
    ...overrides,
  };
}
const catalog = {
  briefing, recent: vi.fn(async () => page([newsItem])), search: vi.fn(async () => page([])),
  sources: vi.fn(async () => sourceCatalog), detail,
};
const auth: AuthSession = {
  signedIn: () => true, signIn: vi.fn(async () => undefined),
  signOut: vi.fn(async () => undefined), token: vi.fn(async () => "fixture"),
};

test("votes show current rating, accept an optional bounded comment and submit once", async () => {
  const feedback = client({ mine: vi.fn(async () => ({ rating: "up" as const, comment: null })) });
  render(<FeedbackControls client={feedback} label="Rate this briefing"
    target={{ type: "briefing", ref: "version-1" }} />);
  expect(await screen.findByText("Your rating: Helpful")).toBeInTheDocument();
  const down = screen.getByRole("button", { name: /Not helpful/ });
  expect(down).toHaveAttribute("aria-pressed", "false");
  fireEvent.click(down);
  expect(down).toHaveAttribute("aria-pressed", "true");
  const box = screen.getByLabelText("Comment (optional)");
  expect(box).toHaveAttribute("maxLength", String(MAX_COMMENT));
  fireEvent.change(box, { target: { value: "  Too generic  " } });
  expect(screen.getByText(`15/${MAX_COMMENT}`)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Send feedback" }));
  expect(await screen.findByText("Thanks, your feedback was recorded.")).toBeInTheDocument();
  expect(feedback.sent).toEqual([{ target: { type: "briefing", ref: "version-1" }, rating: "down", comment: "Too generic" }]);
  expect(screen.getByText("Your rating: Not helpful")).toBeInTheDocument();
});

test("failed or rejected submissions say so without losing the page", async () => {
  const feedback = client({ submit: vi.fn(async () => { throw new UiFailure("invalid_input"); }) });
  render(<FeedbackControls client={feedback} label="Rate" target={{ type: "briefing", ref: "v" }} />);
  fireEvent.click(screen.getByRole("button", { name: /^.*Helpful$/ }));
  fireEvent.click(screen.getByRole("button", { name: "Send feedback" }));
  expect(await screen.findByText(/could not be accepted/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(screen.queryByLabelText("Comment (optional)")).toBeNull();
});

test("briefing panel rates the published version without another briefing read", async () => {
  const feedback = client();
  const read = vi.fn(briefing);
  render(<BriefingPanel catalog={{ ...catalog, briefing: read }} active feedback={feedback} />);
  const group = await screen.findByRole("group", { name: "Rate this briefing" });
  fireEvent.click(within(group).getByRole("button", { name: /Not helpful/ }));
  fireEvent.click(screen.getByRole("button", { name: "Send feedback" }));
  await screen.findByText("Thanks, your feedback was recorded.");
  expect(feedback.sent[0]?.target).toEqual({ type: "briefing", ref: briefingResponse.briefing!.version });
  expect(read).toHaveBeenCalledOnce();
});

test("research answers are rated with the displayed snapshot and no new research", async () => {
  const ask = vi.fn(async function* () {
    yield { kind: "answer" as const, answer: parseAnswer("Gateway changed. [1]\n\n[1] https://publisher.test/a") };
  });
  const research: ResearchClient = { ask, stop: vi.fn(async () => false) };
  const feedback = client();
  render(<App auth={auth} catalog={catalog} research={research} feedback={feedback} />);
  fireEvent.click(screen.getByRole("button", { name: "Agent" }));
  fireEvent.change(screen.getByLabelText("What would you like to understand?"), { target: { value: "What changed?" } });
  fireEvent.click(screen.getByRole("button", { name: "Ask Newsloom" }));
  const group = await screen.findByRole("group", { name: "Rate this answer" });
  fireEvent.click(within(group).getByRole("button", { name: /Not helpful/ }));
  fireEvent.change(screen.getAllByLabelText("Comment (optional)").at(-1)!, { target: { value: "Missed security" } });
  fireEvent.click(screen.getAllByRole("button", { name: "Send feedback" }).at(-1)!);
  await waitFor(() => expect(feedback.sent).toHaveLength(1));
  const [entry] = feedback.sent;
  expect(entry?.target.type).toBe("research");
  expect(entry?.snapshot).toEqual({
    question: "What changed?",
    answer: { paragraphs: [{ text: "Gateway changed.", references: [1] }] },
    citations: [{ number: 1, url: "https://publisher.test/a" }],
    filters: {},
  });
  expect(ask).toHaveBeenCalledOnce();
});

test("review page shows non-reviewers a clear message and renders feedback as text", async () => {
  const denied = client({ review: vi.fn(async () => { throw new UiFailure("authorization"); }) });
  const { unmount } = render(<ReviewPage client={denied} />);
  expect(await screen.findByText("You are not a feedback reviewer.")).toBeInTheDocument();
  unmount();
  const items: ReviewItem[] = [{
    created_at: "2026-11-05T10:00:00Z", target_type: "research", target_ref: "answer-1", rating: "down",
    comment: "<img src=x onerror=bad()>", snapshot: { question: "<b>Q</b>" },
  }];
  const reviewer = client({ review: vi.fn(async () => items), exportLines: vi.fn(async () => "{}\n") });
  const created = vi.fn(() => "blob:feedback");
  vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: created, revokeObjectURL: vi.fn() }));
  render(<ReviewPage client={reviewer} />);
  expect(await screen.findByText("<img src=x onerror=bad()>")).toBeInTheDocument();
  expect(screen.getByText("Question: <b>Q</b>")).toBeInTheDocument();
  expect(document.querySelector("img")).toBeNull();
  fireEvent.change(screen.getByLabelText("Type"), { target: { value: "research" } });
  await waitFor(() => expect(reviewer.review).toHaveBeenLastCalledWith(
    { rating: "down", days: 30, targetType: "research" }, expect.any(AbortSignal)));
  fireEvent.click(screen.getByRole("button", { name: "Export JSONL" }));
  await waitFor(() => expect(created).toHaveBeenCalledOnce());
});

test("HTTP client posts the API contract and maps 400 and 403", async () => {
  const calls: { url: string; init: RequestInit | undefined }[] = [];
  const respond = (status: number, body: string, type = "application/json") => new Response(body, {
    status, headers: { "Content-Type": type },
  });
  const statuses = [201, 400, 403];
  const fetchImpl = vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ url: String(url), init });
    const status = statuses.shift() ?? 200;
    return respond(status, status === 201 ? '{"status":"recorded"}' : '{"error":{"code":"x"}}');
  });
  const http = new HttpFeedback(runtimeConfig, auth, fetchImpl as typeof fetch);
  await http.submit({ target: { type: "briefing", ref: "v1" }, rating: "up", comment: null }, new AbortController().signal);
  expect(calls[0]?.url).toBe(`${runtimeConfig.newsApiUrl}/feedback`);
  expect(JSON.parse(String(calls[0]?.init?.body))).toEqual({
    target_type: "briefing", target_ref: "v1", rating: "up", comment: null,
  });
  await expect(http.submit({ target: { type: "briefing", ref: "v1" }, rating: "up", comment: null },
    new AbortController().signal)).rejects.toMatchObject({ category: "invalid_input" });
  await expect(http.review({ days: 30 }, new AbortController().signal))
    .rejects.toMatchObject({ category: "authorization" });
});
