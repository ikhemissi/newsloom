import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { App } from "../src/App";
import type { AuthSession } from "../src/domain";
import { briefing, newsDetail, newsItem, page, sourceCatalog } from "./fixtures";

const auth: AuthSession = {
  signedIn: () => true, signIn: async () => undefined, signOut: async () => undefined,
  token: async () => "fixture",
};
const future = { ...newsItem, publishedAt: "2026-11-03T00:00:00Z" };
const fixtures = () => ({
  briefing,
  recent: vi.fn(async () => ({ ...page([future]), readAt: future.publishedAt, cacheAgeSeconds: 12.5 })),
  search: vi.fn(async () => page([])), sources: vi.fn(async () => sourceCatalog),
  detail: vi.fn(async () => ({ ...newsDetail, ...future })),
});
const research = () => ({ ask: vi.fn(), stop: vi.fn(async () => false) });

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date", "setInterval", "clearInterval"] });
  vi.setSystemTime(new Date("2026-11-02T23:59:30Z"));
});
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });

test("cards/detail share raw instants and offsets, while only article dates get future indications", async () => {
  const catalog = fixtures();
  const agent = research();
  const { container } = render(<App auth={auth} catalog={catalog} research={agent} />);
  const card = await screen.findByRole("article");
  const time = card.querySelector("time");
  expect(time).toHaveAttribute("datetime", future.publishedAt);
  expect(time?.textContent).toMatch(/GMT|UTC/);
  expect(within(card).getByText("Future-dated")).toBeInTheDocument();
  const metadata = screen.getByRole("region", { name: "Browse continuation" });
  expect(metadata.querySelector("time")).toHaveTextContent(time?.textContent ?? "");
  expect(within(metadata).queryByText("Future-dated")).toBeNull();
  fireEvent.click(screen.getByRole("link", { name: future.title }));
  const detail = await screen.findByRole("region", { name: "News detail" });
  await within(detail).findByText("Authored publisher");
  expect(detail.querySelector("time")).toHaveAttribute("datetime", future.publishedAt);
  expect(detail.querySelector("time")).toHaveTextContent(time?.textContent ?? "");
  expect(within(detail).getByText("Future-dated")).toBeInTheDocument();
  expect(container.querySelectorAll("time[datetime]")).toHaveLength(3);
  expect(agent.ask).not.toHaveBeenCalled();
});

test("future/equal/past and equivalent offset instants preserve the server's item order", async () => {
  const rows = [
    future,
    { ...future, id: crypto.randomUUID(), title: "Equivalent future", publishedAt: "2026-11-03T01:00:00+01:00" },
    { ...future, id: crypto.randomUUID(), title: "Equal time", publishedAt: "2026-11-02T23:59:30Z" },
    { ...future, id: crypto.randomUUID(), title: "Past time", publishedAt: "2026-11-02T23:59:29Z" },
  ];
  render(<App auth={auth} catalog={{ ...fixtures(), recent: async () => page(rows) }} research={research()} />);
  await screen.findByRole("heading", { name: "Past time" });
  const articles = screen.getAllByRole("article");
  expect(articles.map((item) => item.querySelector("h2")?.textContent)).toEqual(rows.map((item) => item.title));
  expect(articles.map((item) => !!within(item).queryByText("Future-dated"))).toEqual([true, true, false, false]);
  expect(articles.map((item) => item.querySelector("time")?.getAttribute("datetime"))).toEqual(rows.map((item) => item.publishedAt));
});

test("minute/focus/visibility updates are display-only and clean up on sign-out and unmount", async () => {
  const catalog = fixtures();
  const agent = research();
  const { unmount } = render(<App auth={auth} catalog={catalog} research={agent} />);
  await screen.findByText("Future-dated");
  expect(vi.getTimerCount()).toBe(1);
  act(() => vi.advanceTimersByTime(60_000));
  expect(screen.queryByText("Future-dated")).toBeNull();
  expect(screen.getByText(/Server read age at response: 12.5 seconds/)).toBeInTheDocument();
  vi.setSystemTime(new Date("2026-11-02T23:59:45Z"));
  fireEvent(window, new Event("focus"));
  expect(screen.getByText("Future-dated")).toBeInTheDocument();
  const visibility = vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden");
  vi.setSystemTime(new Date("2026-11-03T00:00:00Z"));
  fireEvent(document, new Event("visibilitychange"));
  expect(screen.getByText("Future-dated")).toBeInTheDocument();
  visibility.mockReturnValue("visible");
  fireEvent(document, new Event("visibilitychange"));
  expect(screen.queryByText("Future-dated")).toBeNull();
  expect(catalog.recent).toHaveBeenCalledOnce();
  expect(catalog.sources).toHaveBeenCalledOnce();
  expect(catalog.search).not.toHaveBeenCalled();
  expect(catalog.detail).not.toHaveBeenCalled();
  expect(agent.ask).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
  expect(vi.getTimerCount()).toBe(0);
  unmount();
  fireEvent(window, new Event("focus"));
  expect(vi.getTimerCount()).toBe(0);
});

test("unmounting an active clock removes its interval and event subscriptions", async () => {
  const removeWindow = vi.spyOn(window, "removeEventListener");
  const removeDocument = vi.spyOn(document, "removeEventListener");
  const { unmount } = render(<App auth={auth} catalog={fixtures()} research={research()} />);
  await screen.findByRole("article");
  expect(vi.getTimerCount()).toBe(1);
  unmount();
  expect(vi.getTimerCount()).toBe(0);
  expect(removeWindow).toHaveBeenCalledWith("focus", expect.any(Function));
  expect(removeDocument).toHaveBeenCalledWith("visibilitychange", expect.any(Function));
});
