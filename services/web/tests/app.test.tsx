import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { App, AnswerView } from "../src/App";
import { parseAnswer } from "../src/answer";
import { UiFailure } from "../src/domain";
import type { AuthSession, ResearchClient } from "../src/domain";
import { briefing, detail, newsItem, sourceCatalog, page, answerEvent } from "./fixtures";

const catalog = {
  briefing,
  recent: vi.fn(async () => page([newsItem])),
  search: vi.fn(async () => page([])),
  sources: vi.fn(async () => sourceCatalog),
  detail,
};
const openAgent = () => fireEvent.click(screen.getByRole("button", { name: "Agent" }));

vi.stubGlobal("matchMedia", () => ({ matches: false }));
const auth = (signedIn: boolean): AuthSession => ({
  signedIn: () => signedIn, signIn: vi.fn(async () => undefined),
  signOut: vi.fn(async () => undefined), token: vi.fn(async () => "fixture"),
});

test("signed-out readers see a real sign-in action, not fake news", async () => {
  const session = auth(false);
  render(<App auth={session} catalog={catalog} research={{ ask: vi.fn(), stop: vi.fn() }} />);
  expect(screen.getByText(/browse stored news/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Sign in to read news" }));
  await waitFor(() => expect(session.signIn).toHaveBeenCalledOnce());
});

test("lofi is the default theme and the optional dark toggle returns to lofi", () => {
  render(<App auth={auth(false)} catalog={catalog} research={{ ask: vi.fn(), stop: vi.fn() }} />);
  expect(document.documentElement).toHaveAttribute("data-theme", "lofi");
  fireEvent.click(screen.getByRole("button", { name: "Switch to dark theme" }));
  expect(document.documentElement).toHaveAttribute("data-theme", "dark");
  fireEvent.click(screen.getByRole("button", { name: "Switch to lofi theme" }));
  expect(document.documentElement).toHaveAttribute("data-theme", "lofi");
});

test("hostile text is inert and numeric citation controls focus safe references", () => {
  const answer = parseAnswer("<img src=x onerror=bad()> [1]\n\n[1] https://publisher.test/article");
  const { container } = render(<AnswerView answer={answer} />);
  expect(container.querySelector("img")).toBeNull();
  expect(screen.getByText("<img src=x onerror=bad()>")).toBeInTheDocument();
  const link = screen.getByRole("link", { name: /publisher.test/ });
  expect(link).toHaveAttribute("rel", "noopener noreferrer");
  fireEvent.click(screen.getByRole("button", { name: "Focus citation 1" }));
  expect(container.querySelector("li")).toHaveFocus();
});

test("progress precedes the answer and no-match stays visible", async () => {
  const research: ResearchClient = {
    async *ask() {
      yield { kind: "progress", phase: "retrieving" };
      yield answerEvent("No matching stored evidence.\n\nLimitation: no match.");
    },
    stop: vi.fn(async () => false),
  };
  render(<App auth={auth(true)} catalog={catalog} research={research} />);
  openAgent();
  fireEvent.change(screen.getByLabelText("What would you like to understand?"), { target: { value: "Fixture question" } });
  fireEvent.click(screen.getByRole("button", { name: "Ask Newsloom" }));
  expect(await screen.findByText("No matching stored evidence.")).toBeInTheDocument();
  expect(screen.getByText("Limitation: no match.")).toBeInTheDocument();
});

test("authorization failure offers sign-in and never resends the question", async () => {
  const session = auth(true);
  const ask = vi.fn(async function* () { throw new UiFailure("interaction"); });
  render(<App auth={session} catalog={catalog} research={{ ask, stop: vi.fn(async () => false) }} />);
  openAgent();
  fireEvent.change(screen.getByLabelText("What would you like to understand?"), { target: { value: "Fixture question" } });
  fireEvent.click(screen.getByRole("button", { name: "Ask Newsloom" }));
  await waitFor(() => expect(screen.getAllByRole("alert").some((alert) =>
    alert.textContent?.includes("Your question will not be resent"))).toBe(true));
  expect(screen.getByRole("button", { name: "Sign in for research" })).toBeInTheDocument();
  expect(ask).toHaveBeenCalledOnce();
});

test("stopping does not turn partial work into a completed answer or pretend cancellation", async () => {
  let release: (() => void) | undefined;
  const pending = new Promise<void>((resolve) => { release = resolve; });
  const research: ResearchClient = {
    async *ask() {
      yield { kind: "progress", phase: "retrieving" };
      await pending;
      yield answerEvent("Late fixture answer.");
    },
    stop: async () => { release?.(); return false; },
  };
  render(<App auth={auth(true)} catalog={catalog} research={research} />);
  openAgent();
  fireEvent.change(screen.getByLabelText("What would you like to understand?"), { target: { value: "Fixture" } });
  fireEvent.click(screen.getByRole("button", { name: "Ask Newsloom" }));
  const stop = await screen.findByRole("button", { name: "Stop" });
  fireEvent.click(stop);
  expect(await screen.findByRole("alert")).toHaveTextContent("Server cancellation is not yet confirmed");
  expect(screen.queryByLabelText("Research answer")).toBeNull();
});

test("latest news is the default and typing/searching does not invoke the agent", async () => {
  const recent = vi.fn(async () => page([newsItem]));
  const search = vi.fn(async () => page([{ ...newsItem, title: "Ranked fixture result" }]));
  const ask = vi.fn(async function* () { yield answerEvent("Fixture"); });
  render(<App auth={auth(true)} catalog={{ recent, search, sources: catalog.sources, detail, briefing }} research={{ ask, stop: async () => false }} />);
  expect(await screen.findByRole("heading", { name: newsItem.title })).toBeInTheDocument();
  expect(screen.queryByRole("complementary")).toBeNull();
  expect(recent).toHaveBeenCalledOnce();
  fireEvent.change(screen.getByLabelText("Search stored news"), { target: { value: "fixture query" } });
  expect(search).not.toHaveBeenCalled();
  expect(ask).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Search" }));
  expect(await screen.findByRole("heading", { name: "Ranked fixture result" })).toBeInTheDocument();
  expect(search).toHaveBeenCalledWith("fixture query", expect.any(AbortSignal), {});
  expect(ask).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Clear search" }));
  expect(await screen.findByRole("heading", { name: newsItem.title })).toBeInTheDocument();
  expect(recent).toHaveBeenCalledTimes(2);
});

test("right panel uses displayed current-news context and close/reopen does not replay research", async () => {
  const ask = vi.fn(async function* () { yield answerEvent("Fixture answer."); });
  render(<App auth={auth(true)} catalog={catalog} research={{ ask, stop: async () => false }} />);
  const itemAction = await screen.findByRole("button", { name: `Ask about this: ${newsItem.title}` });
  fireEvent.click(itemAction);
  expect(screen.getByRole("complementary", { name: "Agent interactions" })).toBeInTheDocument();
  expect(screen.getByLabelText("What would you like to understand?")).toHaveFocus();
  expect(screen.getByText(`Current news: ${newsItem.title}`)).toBeInTheDocument();
  expect(ask).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("What would you like to understand?"), { target: { value: "Explain this item" } });
  fireEvent.click(screen.getByRole("button", { name: "Ask Newsloom" }));
  expect(await screen.findByText("Fixture answer.")).toBeInTheDocument();
  expect(ask).toHaveBeenCalledWith("Explain this item", expect.any(AbortSignal), [newsItem.id], {}, []);
  fireEvent.click(screen.getByRole("button", { name: "Close agent panel" }));
  expect(itemAction).toHaveFocus();
  expect(screen.queryByRole("complementary")).toBeNull();
  openAgent();
  expect(ask).toHaveBeenCalledOnce();
  expect(screen.getByText("Fixture answer.")).toBeInTheDocument();
});

test("search replaces stale idle context and failures are not successful empty lists", async () => {
  const search = vi.fn(async () => { throw new UiFailure("unavailable"); });
  render(<App auth={auth(true)} catalog={{ recent: async () => page([newsItem]), search, sources: catalog.sources, detail, briefing }}
    research={{ ask: vi.fn(), stop: async () => false }} />);
  fireEvent.click(await screen.findByRole("button", { name: `Ask about this: ${newsItem.title}` }));
  fireEvent.change(screen.getByLabelText("Search stored news"), { target: { value: "fixture" } });
  fireEvent.click(screen.getByRole("button", { name: "Search" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("service is unavailable");
  expect(screen.queryByText(`Current news: ${newsItem.title}`)).toBeNull();
  expect(screen.queryByText("No news matches this search.")).toBeNull();
});

test("sign-out prevents an unfinished read from repopulating news", async () => {
  let release: ((value: typeof newsItem[]) => void) | undefined;
  const pending = new Promise<typeof newsItem[]>((resolve) => { release = resolve; });
  render(<App auth={auth(true)} catalog={{ recent: async () => page(await pending), search: async () => page([]), sources: catalog.sources, detail, briefing }}
    research={{ ask: vi.fn(), stop: async () => false }} />);
  fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
  release?.([newsItem]);
  await waitFor(() => expect(screen.getByRole("button", { name: "Sign in to read news" })).toBeInTheDocument());
  expect(screen.queryByRole("heading", { name: newsItem.title })).toBeNull();
});

test("a conversation keeps its thread, offers follow-ups with history, and starts over on demand", async () => {
  const cited = ["00000000", "0000", "4000", "8000", "000000000001"].join("-");
  const first = "Foundry agents gained hosted resilience. [1]\n\n[1] https://publisher.test/foundry";
  const ask = vi.fn()
    .mockImplementationOnce(async function* () { yield answerEvent(first, { followUps: ["And what about AWS?"], citedItemIds: [cited] }); })
    .mockImplementationOnce(async function* () { yield answerEvent("AWS added AgentCore limits."); });
  render(<App auth={auth(true)} catalog={catalog} research={{ ask, stop: async () => true }} />);
  openAgent();
  fireEvent.change(screen.getByLabelText("What would you like to understand?"), { target: { value: "What changed for Foundry agents?" } });
  fireEvent.click(screen.getByRole("button", { name: "Ask Newsloom" }));
  const followUp = await screen.findByRole("button", { name: "And what about AWS?" });
  expect(screen.getByLabelText("What would you like to understand?")).toHaveValue("");
  fireEvent.click(followUp);
  await screen.findByText("AWS added AgentCore limits.");
  expect(ask).toHaveBeenLastCalledWith("And what about AWS?", expect.any(AbortSignal), undefined, {},
    [{ question: "What changed for Foundry agents?", answer: first, cited_item_ids: [cited] }]);
  const thread = screen.getByRole("list", { name: "Conversation" });
  expect(thread.children).toHaveLength(2);
  expect(JSON.parse(sessionStorage.getItem("newsloom.conversation") ?? "[]")).toHaveLength(2);
  fireEvent.click(screen.getByRole("button", { name: "New conversation" }));
  expect(screen.queryByRole("list", { name: "Conversation" })).toBeNull();
  expect(sessionStorage.getItem("newsloom.conversation")).toBeNull();
});

test("sign-out removes the stored conversation", async () => {
  sessionStorage.setItem("newsloom.conversation", JSON.stringify([{ id: "t1", question: "Q?", text: "A.",
    followUps: [], citedItemIds: [] }]));
  render(<App auth={auth(true)} catalog={catalog} research={{ ask: vi.fn(), stop: async () => true }} />);
  openAgent();
  expect(screen.getByRole("list", { name: "Conversation" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
  await waitFor(() => expect(sessionStorage.getItem("newsloom.conversation")).toBeNull());
});

test("a failed research request is reported inside the panel and the question is kept", async () => {
  const ask = vi.fn(async function* () { throw new UiFailure("unavailable"); });
  render(<App auth={auth(true)} catalog={catalog} research={{ ask, stop: async () => true }} />);
  openAgent();
  fireEvent.change(screen.getByLabelText("What would you like to understand?"), { target: { value: "And what about AWS?" } });
  fireEvent.click(screen.getByRole("button", { name: "Ask Newsloom" }));
  const panel = screen.getByRole("complementary");
  expect(await within(panel).findByRole("alert")).toHaveTextContent("The service is unavailable");
  expect(screen.getByLabelText("What would you like to understand?")).toHaveValue("And what about AWS?");
});
