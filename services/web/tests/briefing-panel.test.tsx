import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { BriefingPanel } from "../src/BriefingPanel";
import { App } from "../src/App";
import type { BriefingResponse, NewsCatalog } from "../src/domain";
import { UiFailure } from "../src/domain";
import { parseAnswer } from "../src/answer";
import { architectBriefing, briefing, briefingResponse, detail, legacyBriefing, newsItem, noMaterialBriefing, page, sourceCatalog } from "./fixtures";

const catalog = (read = vi.fn(briefing)): NewsCatalog => ({
  briefing: read, recent: async () => page([newsItem]), search: async () => page([]),
  sources: async () => sourceCatalog, detail,
});
const flush = async () => { await act(async () => undefined); };
const open = () => fireEvent.click(screen.getByRole("button", { name: "Agent" }));
const tick = async (ms: number) => { await act(async () => { await vi.advanceTimersByTimeAsync(ms); }); };
const summary = () => screen.getByText(/Full briefing and sources · About \d+ minutes?/).closest("details")!;
beforeEach(() => {
  vi.useFakeTimers(); vi.setSystemTime(new Date("2026-11-02T12:00:00Z"));
});
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });

test("only open panels read, throttle reopen/focus/retry, retain same-version expansion and collapse new versions", async () => {
  const next = structuredClone(briefingResponse);
  next.briefing!.version = crypto.randomUUID(); next.briefing!.tldr!.text = "Updated authored overview.";
  const read = vi.fn(briefing).mockResolvedValueOnce(structuredClone(briefingResponse))
    .mockResolvedValueOnce(structuredClone(briefingResponse)).mockResolvedValue(next);
  const source = catalog(read);
  const { rerender } = render(<BriefingPanel catalog={source} active={false} />);
  await tick(120_000); expect(read).not.toHaveBeenCalled();
  rerender(<BriefingPanel catalog={source} active />); await flush();
  expect(read).toHaveBeenCalledOnce(); expect(summary().open).toBe(false);
  summary().open = true;
  fireEvent(window, new Event("focus")); fireEvent(document, new Event("visibilitychange"));
  await flush(); expect(read).toHaveBeenCalledOnce();
  rerender(<BriefingPanel catalog={source} active={false} />);
  rerender(<BriefingPanel catalog={source} active />); await flush();
  expect(read).toHaveBeenCalledOnce(); expect(summary().open).toBe(true);
  await tick(60_000); expect(read).toHaveBeenCalledTimes(2); expect(summary().open).toBe(true);
  await tick(60_000); expect(read).toHaveBeenCalledTimes(3); expect(summary().open).toBe(false);
  expect(screen.getByText("Updated authored overview.")).toBeInTheDocument();
});

test("close and sign-out/teardown abort owned reads and ignore even uncancellable late results", async () => {
  let resolve: (value: BriefingResponse) => void = () => undefined;
  let owned: AbortSignal | undefined;
  const source: NewsCatalog = { ...catalog(), briefing: vi.fn((signal) => {
    owned = signal; return new Promise<BriefingResponse>((done) => { resolve = done; });
  }) };
  const { rerender, unmount } = render(<BriefingPanel catalog={source} active />);
  rerender(<BriefingPanel catalog={source} active={false} />);
  expect(owned?.aborted).toBe(true);
  await act(async () => resolve(briefingResponse));
  expect(screen.queryByText(/Authored weekly overview/)).toBeNull();
  await tick(60_000);
  rerender(<BriefingPanel catalog={source} active />);
  unmount(); expect(owned?.aborted).toBe(true);
  await act(async () => resolve(briefingResponse));
});

test("resumption reads only while visible/open and never more than once a minute", async () => {
  let visibility = "visible";
  vi.spyOn(document, "visibilityState", "get").mockImplementation(() => visibility as DocumentVisibilityState);
  const read = vi.fn(briefing);
  const source = catalog(read);
  const { rerender } = render(<BriefingPanel catalog={source} active />);
  await flush(); expect(read).toHaveBeenCalledOnce();
  visibility = "hidden"; await tick(120_000);
  expect(read).toHaveBeenCalledOnce();
  visibility = "visible"; fireEvent(document, new Event("visibilitychange")); await flush();
  expect(read).toHaveBeenCalledTimes(2);
  fireEvent(window, new Event("focus")); await flush(); expect(read).toHaveBeenCalledTimes(2);
  rerender(<BriefingPanel catalog={source} active={false} />);
  await tick(120_000); fireEvent(window, new Event("focus")); await flush();
  expect(read).toHaveBeenCalledTimes(2);
  rerender(<BriefingPanel catalog={source} active />); await flush();
  expect(read).toHaveBeenCalledTimes(3);
});

test("read failures remain visible and retryable; pending, stale, failed and no-news stay distinct", async () => {
  const pending = { ...structuredClone(briefingResponse), briefing: null,
    refresh: { ...briefingResponse.refresh, stale: true, state: "running" as const } };
  const stale = structuredClone(briefingResponse);
  stale.refresh = { expected_cutoff: "2026-11-03T05:00:00Z", stale: true, state: "failed" };
  const empty = structuredClone(briefingResponse);
  empty.briefing = { ...empty.briefing!, coverage: "empty", evidence_count: 0, tldr: null, sections: [], citations: [] };
  const read = vi.fn(briefing).mockRejectedValueOnce(new UiFailure("unavailable"))
    .mockResolvedValueOnce(pending).mockResolvedValueOnce(stale).mockRejectedValueOnce(new UiFailure("authorization"))
    .mockResolvedValueOnce(empty);
  render(<BriefingPanel catalog={catalog(read)} active />); await flush();
  expect(screen.getByRole("alert")).toHaveTextContent("Briefing read failed");
  fireEvent.click(screen.getByRole("button", { name: "Retry briefing" })); await flush();
  expect(read).toHaveBeenCalledOnce();
  await tick(60_000);
  expect(screen.getByText(/No published briefing is available yet/)).toBeInTheDocument();
  expect(screen.queryByText(/No stored news/)).toBeNull();
  await tick(60_000);
  expect(screen.getByText(/Briefing refresh failed/)).toHaveTextContent("stale");
  expect(screen.getByText(/Authored weekly overview/)).toBeInTheDocument();
  await tick(60_000);
  expect(screen.getByRole("alert")).toHaveTextContent("Access was denied");
  expect(screen.getByText(/freshness could not be checked/)).toBeInTheDocument();
  await tick(60_000);
  expect(screen.getByText(/No stored news was available/)).toBeInTheDocument();
  expect(screen.queryByText(/No published briefing/)).toBeNull();
  expect(screen.queryByRole("alert")).toBeNull();
});

test.each([
  ["short architect", architectBriefing(), "About 1 minute"],
  ["ceiling architect", architectBriefing(920, 80), "About 5 minutes"],
  ["legacy 1026 plus 82", legacyBriefing(), "About 6 minutes"],
])("%s shows only local generation metadata before TLDR and estimates all prose", async (_name, result, readingTime) => {
  const read = vi.fn(async () => result);
  const { container } = render(<BriefingPanel catalog={catalog(read)} active />);
  await flush();
  const region = screen.getByRole("region", { name: "Daily news briefing" });
  expect([...region.children].map((child) => child.tagName)).toEqual(["H3", "P", "DIV", "DETAILS"]);
  expect(region.children[1]).toHaveTextContent("Generated:");
  expect(region.children[2]).toHaveClass("briefing-tldr");
  expect(region.querySelectorAll("time")).toHaveLength(1);
  expect(region.querySelector("time")).toHaveAttribute("datetime", result.briefing!.generated_at);
  expect(region.textContent).not.toMatch(/Daily refresh|Expected daily cutoff|Evidence window|stored records|Last read|cache age|Generated overview/);
  expect(summary()).toHaveTextContent(readingTime);
  expect(summary().open).toBe(false);
  summary().open = true;
  await flush();
  expect(container.querySelectorAll("details section p")).toHaveLength(result.briefing!.sections[0]!.paragraphs.length);
  expect(read).toHaveBeenCalledOnce();
});

test("no-material publication has an honest concise notice without a fake TLDR or sources", async () => {
  render(<BriefingPanel catalog={catalog(vi.fn(async () => noMaterialBriefing()))} active />);
  await flush();
  const region = screen.getByRole("region", { name: "Daily news briefing" });
  expect(region).toHaveTextContent("No material changes were identified in reviewed stored reporting.");
  expect(region.querySelector(".briefing-tldr, details, a")).toBeNull();
  expect(region.textContent).not.toMatch(/No stored news|No published briefing|failed/);
});

test("a background read does not add healthy loading or diagnostic clutter", async () => {
  const read = vi.fn(briefing).mockResolvedValueOnce(architectBriefing())
    .mockImplementationOnce(() => new Promise<BriefingResponse>(() => undefined));
  render(<BriefingPanel catalog={catalog(read)} active />);
  await flush();
  await tick(60_000);
  expect(read).toHaveBeenCalledTimes(2);
  const region = screen.getByRole("region", { name: "Daily news briefing" });
  expect([...region.children].map((child) => child.tagName)).toEqual(["H3", "P", "DIV", "DETAILS"]);
  expect(region.querySelectorAll("time")).toHaveLength(1);
  expect(region.textContent).not.toMatch(/Reading the published briefing|Daily refresh|Last read|cache age/);
});

test("App keeps composer, selected news, answer/context and panel scroll independent of briefing reads", async () => {
  const updated = structuredClone(briefingResponse);
  updated.briefing!.version = crypto.randomUUID();
  const source = catalog(vi.fn(briefing)
    .mockResolvedValueOnce(structuredClone(briefingResponse))
    .mockResolvedValueOnce(structuredClone(briefingResponse)).mockResolvedValue(updated));
  const ask = vi.fn(async function* () {
    yield { kind: "answer" as const, answer: parseAnswer("Authored retained research answer.") };
  });
  const session = {
    signedIn: () => true, signIn: async () => undefined, signOut: vi.fn(async () => undefined),
    token: async () => "fixture",
  };
  const { container } = render(<App auth={session} catalog={source} research={{ ask, stop: async () => false }} />);
  await flush();
  expect(screen.queryByLabelText("Daily news briefing")).not.toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: `Ask about this: ${newsItem.title}` })); await flush();
  const region = screen.getByRole("region", { name: "Daily news briefing" });
  const panel = screen.getByRole("complementary");
  const children = [...panel.children];
  expect(children.indexOf(region)).toBe(1);
  expect(container.querySelector("img, svg")).toBeNull();
  const question = screen.getByLabelText("What would you like to understand?");
  fireEvent.change(question, { target: { value: "Keep authored input" } });
  fireEvent.click(screen.getByRole("button", { name: "Ask Newsloom" })); await flush();
  panel.scrollTop = 137;
  summary().open = true;
  fireEvent.click(within(region).getAllByRole("button", { name: "Focus briefing citation 1" })[0]!);
  expect(region.querySelector("li")).toHaveFocus();
  expect(region.querySelector("a")).toHaveAttribute("rel", "noopener noreferrer");
  await tick(60_000);
  expect(panel.scrollTop).toBe(137); expect(summary().open).toBe(true);
  expect(question).toHaveValue("Keep authored input");
  expect(screen.getByLabelText("Submitted research context")).toHaveTextContent(newsItem.title);
  expect(screen.getByLabelText("Research answer")).toHaveTextContent("Authored retained research answer");
  fireEvent.click(screen.getByRole("button", { name: "Close agent panel" })); open(); await flush();
  expect(summary().open).toBe(true); expect(question).toHaveValue("Keep authored input");
  panel.scrollTop = 137;
  expect(question).toHaveFocus();
  await tick(60_000);
  expect(summary().open).toBe(false); expect(panel.scrollTop).toBe(137);
  expect(question).toHaveFocus(); expect(question).toHaveValue("Keep authored input");
  expect(screen.getByLabelText("Research answer")).toHaveTextContent("Authored retained research answer");
  expect(screen.getByLabelText("Submitted research context")).toHaveTextContent(newsItem.title);
  expect(ask).toHaveBeenCalledOnce();
  fireEvent.click(screen.getByRole("button", { name: "Sign out" })); await flush();
  expect(screen.queryByLabelText("Daily news briefing")).toBeNull();
});

test("signed-out App never starts briefing reads", async () => {
  const read = vi.fn(briefing);
  render(<App auth={{
    signedIn: () => false, signIn: async () => undefined, signOut: async () => undefined, token: async () => "fixture",
  }} catalog={catalog(read)} research={{ ask: vi.fn(), stop: async () => false }} />);
  await tick(120_000); expect(read).not.toHaveBeenCalled();
});

test("closing the panel cancels only its briefing read, not in-flight research; sign-out discards late content", async () => {
  let finishBriefing: (value: BriefingResponse) => void = () => undefined;
  let finishResearch: () => void = () => undefined;
  let researchSignal: AbortSignal | undefined;
  let briefingSignal: AbortSignal | undefined;
  const pendingResearch = new Promise<void>((resolve) => { finishResearch = resolve; });
  const source: NewsCatalog = { ...catalog(), briefing: vi.fn((signal) => {
    briefingSignal = signal;
    return new Promise<BriefingResponse>((resolve) => { finishBriefing = resolve; });
  }) };
  const ask = vi.fn(async function* (_question: string, signal: AbortSignal) {
    researchSignal = signal;
    yield { kind: "progress" as const, phase: "retrieving" as const };
    await pendingResearch;
    yield { kind: "answer" as const, answer: parseAnswer("Independent completed answer.") };
  });
  const stop = vi.fn(async () => false);
  render(<App auth={{
    signedIn: () => true, signIn: async () => undefined, signOut: async () => undefined, token: async () => "fixture",
  }} catalog={source} research={{ ask, stop }} />);
  await flush(); open(); await flush();
  fireEvent.change(screen.getByLabelText("What would you like to understand?"), { target: { value: "Keep working" } });
  fireEvent.click(screen.getByRole("button", { name: "Ask Newsloom" })); await flush();
  fireEvent.click(screen.getByRole("button", { name: "Close agent panel" }));
  expect(briefingSignal?.aborted).toBe(true);
  expect(researchSignal?.aborted).toBe(false); expect(stop).not.toHaveBeenCalled();
  await act(async () => { finishBriefing(briefingResponse); finishResearch(); });
  open(); await flush();
  expect(screen.getByLabelText("Research answer")).toHaveTextContent("Independent completed answer");
  expect(screen.queryByText(/Authored weekly overview/)).toBeNull();
  await tick(60_000);
  fireEvent.click(screen.getByRole("button", { name: "Sign out" })); await flush();
  expect(briefingSignal?.aborted).toBe(true);
  await act(async () => finishBriefing(briefingResponse));
  expect(screen.queryByLabelText("Daily news briefing")).toBeNull();
  expect(ask).toHaveBeenCalledOnce();
});
