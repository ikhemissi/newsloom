import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { App } from "../src/App";
import { parseAnswer } from "../src/answer";
import type { AuthSession, NewsFilters, ResearchClient, SourceCatalog } from "../src/domain";
import { UiFailure } from "../src/domain";
import { buildFilters, emptyDraft } from "../src/filters";
import { detail, newsItem, sourceCatalog, page } from "./fixtures";

const auth: AuthSession = {
  signedIn: () => true, signIn: async () => undefined, signOut: async () => undefined,
  token: async () => "fixture",
};
const research = () => ({ ask: vi.fn(), stop: async () => false });
const choicesReady = () => screen.findByRole("option", { name: "Agents and applications" });
const change = (label: string, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } });
const click = (name: string) => fireEvent.click(screen.getByRole("button", { name }));

test("draft edits dispatch nothing; Apply, Search, Reset and Clear preserve their distinct snapshots", async () => {
  const recent = vi.fn(async () => page([newsItem]));
  const search = vi.fn(async (_query: string | undefined, _signal: AbortSignal, filters: NewsFilters = {}) =>
    page(filters.category === "models" ? [] : [newsItem]));
  const sources = vi.fn(async () => sourceCatalog);
  const agent = research();
  render(<App auth={auth} catalog={{ recent, search, sources, detail }} research={agent} />);
  await choicesReady();
  change("Source", "fixture-source"); change("Category", "agents-applications");
  change("Search stored news", "unsent text");
  expect(search).not.toHaveBeenCalled(); expect(agent.ask).not.toHaveBeenCalled();
  click("Apply filters");
  await waitFor(() => expect(search).toHaveBeenCalledWith(undefined, expect.any(AbortSignal),
    { source: "fixture-source", category: "agents-applications" }));
  await screen.findByRole("heading", { name: newsItem.title });
  change("Search stored news", "submitted query"); click("Search");
  await waitFor(() => expect(search).toHaveBeenLastCalledWith("submitted query", expect.any(AbortSignal),
    { source: "fixture-source", category: "agents-applications" }));
  await screen.findByRole("heading", { name: newsItem.title });
  change("Search stored news", "different unsent text"); change("Category", "models");
  click("Apply filters");
  await screen.findByText("No news matches this search.");
  expect(search).toHaveBeenLastCalledWith("submitted query", expect.any(AbortSignal),
    { source: "fixture-source", category: "models" });
  click("Reset filters");
  await screen.findByRole("heading", { name: newsItem.title });
  expect(search).toHaveBeenLastCalledWith("submitted query", expect.any(AbortSignal), {});
  change("Source", "fixture-source"); click("Apply filters");
  await screen.findByRole("heading", { name: newsItem.title });
  change("Category", "models");
  expect(within(screen.getByRole("form", { name: "News filters" })).getByRole("button", { name: "Clear search" }))
    .toHaveAttribute("type", "button");
  click("Clear search");
  await waitFor(() => expect(search).toHaveBeenLastCalledWith(undefined, expect.any(AbortSignal), { source: "fixture-source" }));
  expect(search).toHaveBeenCalledTimes(6);
  expect(recent).toHaveBeenCalledOnce(); expect(sources).toHaveBeenCalledOnce();
  expect(agent.ask).not.toHaveBeenCalled();
});

test("compact toolbar refresh ignores unsent query, category and invalid date drafts", async () => {
  const recent = vi.fn(async () => page([newsItem]));
  const search = vi.fn(async () => page([newsItem]));
  const agent = research();
  render(<App auth={auth} catalog={{ recent, search, sources: async () => sourceCatalog, detail }} research={agent} />);
  await choicesReady();
  expect(screen.queryByText("STORED NEWS. CLEARER CONTEXT.")).toBeNull();
  expect(screen.queryByText("Stored articles, newest first. Initially showing up to 20.")).toBeNull();
  expect(screen.getByRole("heading", { name: "Latest news" })).toHaveClass("sr-only");
  const toolbar = within(screen.getByRole("form", { name: "News filters" }));
  const refresh = toolbar.getByRole("button", { name: "Refresh" });
  expect(refresh).toHaveAttribute("type", "button");
  change("Source", "fixture-source"); click("Apply filters");
  await screen.findByRole("heading", { name: newsItem.title });
  expect(search).toHaveBeenCalledOnce();
  change("Search stored news", "unsent query"); change("Category", "models"); change("Date period", "custom");
  click("Refresh");
  await screen.findByRole("heading", { name: newsItem.title });
  expect(search).toHaveBeenCalledTimes(2);
  expect(search).toHaveBeenLastCalledWith(undefined, expect.any(AbortSignal), { source: "fixture-source" });
  expect(screen.queryByRole("alert")).toBeNull();
  expect(recent).toHaveBeenCalledOnce();
  expect(agent.ask).not.toHaveBeenCalled();
});

test("invalid custom dates are visible before dispatch and valid one-day ranges use shared mapping", async () => {
  const search = vi.fn(async () => page([newsItem]));
  render(<App auth={auth} catalog={{ recent: async () => page([newsItem]), search,
    sources: async () => sourceCatalog, detail }} research={research()} />);
  await choicesReady();
  change("Date period", "custom"); click("Apply filters");
  expect(await screen.findByRole("alert")).toHaveTextContent("valid, complete dates");
  expect(search).not.toHaveBeenCalled();
  change("Start date", "2026-11-02"); change("End date", "2026-11-01"); click("Apply filters");
  expect(search).not.toHaveBeenCalled();
  change("Start date", "2026-11-01"); click("Apply filters");
  const expected = buildFilters({ ...emptyDraft, period: "custom", start: "2026-11-01", end: "2026-11-01" }, null);
  await waitFor(() => expect(search).toHaveBeenCalledWith(undefined, expect.any(AbortSignal), expected.filters));
  expect(within(screen.getByLabelText("Applied news filters")).getByText(/2026-11-01 to 2026-11-01/)).toBeInTheDocument();
});

test("catalogue failure disables choices, permits dates, and retry does not relax applied filters", async () => {
  const sources = vi.fn(async (): Promise<SourceCatalog> => sourceCatalog)
    .mockRejectedValueOnce(new UiFailure("unavailable"))
    .mockRejectedValueOnce(new UiFailure("unavailable"))
    .mockResolvedValue(sourceCatalog);
  const search = vi.fn(async () => page([]));
  render(<App auth={auth} catalog={{ recent: async () => page([newsItem]), search, sources, detail }} research={research()} />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Source/category choices unavailable");
  expect(screen.getByLabelText("Source")).toBeDisabled();
  change("Date period", "today"); click("Apply filters");
  await screen.findByText("No news matches these filters.");
  const snapshot = search.mock.calls[0];
  click("Retry catalogue");
  await screen.findByRole("button", { name: "Retry catalogue" });
  expect(search).toHaveBeenCalledOnce();
  expect(snapshot).toEqual(search.mock.calls[0]);
  click("Retry catalogue");
  await choicesReady();
  expect(screen.getByLabelText("Source")).toBeEnabled();
  expect(within(screen.getByLabelText("Applied news filters")).getByText(/Today:/)).toBeInTheDocument();
});

test("in-flight and completed research retain exact context despite subsequent browsing changes", async () => {
  let release: (() => void) | undefined;
  const pending = new Promise<void>((resolve) => { release = resolve; });
  const ask = vi.fn(async function* () {
    yield { kind: "progress" as const, phase: "retrieving" as const };
    await pending;
    yield { kind: "answer" as const, answer: parseAnswer("Original scoped fixture answer.") };
  });
  const agent: ResearchClient = { ask, stop: async () => false };
  render(<App auth={auth} catalog={{ recent: async () => page([newsItem]), sources: async () => sourceCatalog, detail,
    search: async (_query, _signal, filters) => page(filters?.category === "models" ? [] : [newsItem]) }} research={agent} />);
  await choicesReady();
  change("Source", "fixture-source"); click("Apply filters");
  await screen.findByRole("heading", { name: newsItem.title });
  click(`Ask about this: ${newsItem.title}`);
  change("What would you like to understand?", "Independent question"); click("Ask Newsloom");
  await screen.findByText("Context used for this request");
  expect(ask).toHaveBeenCalledWith("Independent question", expect.any(AbortSignal), [newsItem.id], { source: "fixture-source" });
  change("Category", "models"); click("Apply filters");
  await screen.findByText("No news matches these filters.");
  expect(within(screen.getByLabelText("Next research filters")).getByText("Category: Models")).toBeInTheDocument();
  expect(within(screen.getByLabelText("Submitted research context")).getByText("Any category")).toBeInTheDocument();
  release?.();
  await screen.findByText("Original scoped fixture answer.");
  click("Reset filters");
  await screen.findByRole("heading", { name: newsItem.title });
  click("Remove news context");
  expect(screen.getByText("Original scoped fixture answer.")).toBeInTheDocument();
  expect(within(screen.getByLabelText("Submitted research context")).getByText(`Submitted news: ${newsItem.title}`)).toBeInTheDocument();
  click("Close agent panel"); click("Agent");
  expect(ask).toHaveBeenCalledOnce();
});

test("sign-out aborts catalogue discovery and discards its late result", async () => {
  let release: ((value: SourceCatalog) => void) | undefined;
  const pending = new Promise<SourceCatalog>((resolve) => { release = resolve; });
  const sources = vi.fn((signal: AbortSignal) => {
    expect(signal.aborted).toBe(false);
    return pending;
  });
  render(<App auth={auth} catalog={{ recent: async () => page([]), search: async () => page([]), sources, detail }} research={research()} />);
  click("Sign out"); release?.(sourceCatalog);
  await screen.findByRole("button", { name: "Sign in to read news" });
  expect(sources.mock.calls[0]?.[0].aborted).toBe(true);
  expect(screen.queryByLabelText("Source")).toBeNull();
});
