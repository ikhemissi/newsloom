import { fireEvent, render, screen, waitFor, within, act } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { App } from "../src/App";
import { UiFailure } from "../src/domain";
import type { AuthSession, NewsFilters, NewsPage } from "../src/domain";
import { newsRoute, returnPath } from "../src/navigation";
import { detail, newsDetail, newsItem, page, sourceCatalog } from "./fixtures";

const auth: AuthSession = {
  signedIn: () => true, signIn: async () => undefined, signOut: async () => undefined,
  token: async () => "fixture",
};
const research = () => ({ ask: vi.fn(), stop: async () => false });
const catalog = {
  recent: async () => page([newsItem]), search: async () => page([]),
  sources: async () => sourceCatalog, detail,
};
const click = (name: string) => fireEvent.click(screen.getByRole("button", { name }));
const item = (index: number) => ({
  ...newsItem, id: newsItem.id.slice(0, 24) + String(index).padStart(12, "0"), title: `Fixture item ${index}`,
});
const batch = (start: number, next: string | null) => page(Array.from({ length: 20 }, (_, i) => item(start + i)), next);

test("navigation only accepts root and canonical UUID detail paths", () => {
  expect(newsRoute("/")).toEqual({ kind: "news" });
  expect(newsRoute(`/news/${newsItem.id}`)).toEqual({ kind: "detail", id: newsItem.id });
  for (const bad of ["/news/not-a-uuid", "//attacker.test", "/news/../../private", "/other"])
    expect(returnPath(bad)).toBe("/");
});

test("Load more is explicit, uses applied filters, caps exactly 200 and restarts without implying exhaustion", async () => {
  const search = vi.fn(async (_query: string | undefined, _signal: AbortSignal, filters?: NewsFilters, cursor?: string) => {
    expect(filters).toEqual({});
    const start = Number(cursor?.replace("page_", ""));
    return batch(start === 160 ? 155 : start, `page_${start + 20}`);
  });
  const recent = vi.fn(async () => batch(0, "page_20"));
  const agent = research();
  render(<App auth={auth} catalog={{ ...catalog, recent, search }} research={agent} />);
  const continuation = within(await screen.findByRole("region", { name: "Browse continuation" }));
  await continuation.findByText("20 stored items displayed.");
  fireEvent.change(screen.getByLabelText("Category"), { target: { value: "models" } });
  expect(search).not.toHaveBeenCalled();
  for (const count of [40, 60, 80, 100, 120, 140, 160, 175, 195, 200]) {
    fireEvent.click(continuation.getByRole("button", { name: "Load more" }));
    await continuation.findByText(`${count} stored items displayed.`);
  }
  expect(search).toHaveBeenCalledTimes(10);
  expect(continuation.queryByRole("button", { name: "Load more" })).toBeNull();
  expect(continuation.getByText("Display limit reached: 200 items. More news may exist.")).toBeInTheDocument();
  expect(continuation.queryByText("No more pages are currently available.")).toBeNull();
  fireEvent.click(continuation.getByRole("button", { name: "Restart browsing" }));
  await screen.findByText("20 stored items displayed.");
  expect(recent).toHaveBeenCalledTimes(2);
  expect(agent.ask).not.toHaveBeenCalled();
}, 15000);

test("append errors retain cards and retry; overlaps are unique and exhausted pages end", async () => {
  const search = vi.fn(async () => page([newsItem, item(1)], null))
    .mockRejectedValueOnce(new UiFailure("unavailable"));
  render(<App auth={auth} catalog={{ ...catalog, recent: async () => page([newsItem], "cursor_1"), search }} research={research()} />);
  await screen.findByText("1 stored items displayed.");
  click("Load more");
  await screen.findByRole("alert");
  expect(screen.getByRole("heading", { name: newsItem.title })).toBeInTheDocument();
  click("Retry Load more");
  await screen.findByText("2 stored items displayed.");
  expect(screen.getAllByRole("article")).toHaveLength(2);
  expect(screen.getByText("No more pages are currently available.")).toBeInTheDocument();
});

test("repeated continuation cycles fail without appending or replaying requests", async () => {
  const search = vi.fn(async () => page([item(1)], "cursor_2"))
    .mockResolvedValueOnce(page([item(1)], "cursor_2"))
    .mockResolvedValueOnce(page([item(2)], "cursor_1"));
  render(<App auth={auth} catalog={{ ...catalog, recent: async () => page([newsItem], "cursor_1"), search }} research={research()} />);
  await screen.findByText("1 stored items displayed.");
  click("Load more");
  await screen.findByText("2 stored items displayed.");
  click("Load more");
  await screen.findByRole("alert");
  expect(screen.queryByRole("heading", { name: "Fixture item 2" })).toBeNull();
  expect(search).toHaveBeenCalledTimes(2);
});

test("new browsing cancels append and ignores its late results", async () => {
  let release: ((value: NewsPage) => void) | undefined;
  const pending = new Promise<NewsPage>((resolve) => { release = resolve; });
  const search = vi.fn(() => pending);
  const recent = vi.fn(async () => page([newsItem], "cursor_1"));
  render(<App auth={auth} catalog={{ ...catalog, recent, search }} research={research()} />);
  await screen.findByText("1 stored items displayed.");
  click("Load more");
  click("Refresh");
  await waitFor(() => expect(recent).toHaveBeenCalledTimes(2));
  release?.(page([item(1)], null));
  await screen.findByText("1 stored items displayed.");
  expect(screen.queryByRole("heading", { name: "Fixture item 1" })).toBeNull();
});

test("detail pages use stored metadata, restore browser history and never auto-send research", async () => {
  const lookup = vi.fn(async () => newsDetail);
  const agent = research();
  render(<App auth={auth} catalog={{ ...catalog, detail: lookup }} research={agent} />);
  fireEvent.click(await screen.findByRole("link", { name: newsItem.title }));
  const view = await screen.findByRole("region", { name: "News detail" });
  expect(window.location.pathname).toBe(`/news/${newsItem.id}`);
  await waitFor(() => expect(within(view).getByText("Authored publisher")).toBeInTheDocument());
  expect(lookup).toHaveBeenCalledWith(newsItem.id, expect.any(AbortSignal));
  fireEvent.click(within(view).getByRole("button", { name: `Ask about this: ${newsItem.title}` }));
  expect(agent.ask).not.toHaveBeenCalled();
  click("Close agent panel");
  expect(within(view).getByRole("button", { name: `Ask about this: ${newsItem.title}` })).toHaveFocus();
  click("Back to news");
  await waitFor(() => expect(window.location.pathname).toBe("/"));
  expect(screen.getByRole("link", { name: newsItem.title })).toHaveFocus();
  act(() => window.history.forward());
  await waitFor(() => expect(window.location.pathname).toBe(`/news/${newsItem.id}`));
  expect(agent.ask).not.toHaveBeenCalled();
});

test("direct detail distinguishes absent data and sign-out discards late detail", async () => {
  window.history.replaceState(null, "", `/news/${newsItem.id}`);
  const recent = vi.fn(catalog.recent);
  const lookup = vi.fn(async () => null);
  const { unmount } = render(<App auth={auth} catalog={{ ...catalog, recent, detail: lookup }} research={research()} />);
  await screen.findByText("This stored news item was not found.");
  expect(recent).not.toHaveBeenCalled();
  click("Back to news");
  await screen.findByRole("heading", { name: "Latest news" });
  unmount();
  window.history.replaceState(null, "", `/news/${newsItem.id}`);
  let release: ((value: typeof newsDetail) => void) | undefined;
  const pending = new Promise<typeof newsDetail>((resolve) => { release = resolve; });
  render(<App auth={auth} catalog={{ ...catalog, detail: () => pending }} research={research()} />);
  click("Sign out"); release?.(newsDetail);
  await screen.findByRole("button", { name: "Sign in to read news" });
  expect(screen.queryByRole("region", { name: "News detail" })).toBeNull();
  expect(window.location.pathname).toBe("/");
});
