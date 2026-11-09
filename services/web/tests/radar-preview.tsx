// Local radar mock-up on the private triage preview fixture; never deployed or committed with data.
import { createRoot } from "react-dom/client";
import { App } from "../src/App";
import { parseAnswer } from "../src/answer";
import type { AuthSession, NewsItem, ResearchClient } from "../src/domain";
import { briefing, newsDetail, page, sourceCatalog } from "./fixtures";
import { FixtureRadar } from "./radar-fixture";
import type { FixtureCard } from "./radar-fixture";
import "../src/style.css";

const path = import.meta.env.VITE_RADAR_FIXTURE as string | undefined;
const root = document.getElementById("root");
if (!root) throw new Error("Missing mock-up root");
if (!path) {
  root.textContent = "Start the mock-up with bash scripts/radar-mock.sh";
} else {
  const cards = ((await (await fetch(`/@fs${path}`)).json()) as { cards: FixtureCard[] }).cards;
  const latest = Math.max(...cards.map((card) => Date.parse(card.published_at)));
  const radar = new FixtureRadar(cards, () => new Date(latest + 12 * 3_600_000));
  const seen = new Set<string>();
  const items: NewsItem[] = cards.filter((card) => !seen.has(card.news_id) && seen.add(card.news_id))
    .sort((left, right) => right.published_at.localeCompare(left.published_at))
    .map((card) => ({ id: crypto.randomUUID(), title: card.title, summary: card.statement,
      source: card.source, category: "agents-applications", publishedAt: card.published_at, url: card.url }));
  const auth: AuthSession = {
    signedIn: () => true, signIn: async () => undefined, signOut: async () => undefined,
    token: async () => "mock-up",
  };
  const research: ResearchClient = {
    async *ask(question) {
      yield { kind: "progress", phase: "retrieving" };
      yield { kind: "answer", answer: parseAnswer(
        `Mock-up answer to "${question}". The conversation panel is the next change.\n\n[1] https://publisher.test/article`) };
    },
    stop: async () => false,
  };
  // A mock briefing from the week's act-now cards; the real header shows the published briefing.
  const top = cards.filter((card) => card.tier === "act_now").slice(0, 4);
  const mockBriefing = async () => ({
    ...(await briefing()),
    briefing: { ...(await briefing()).briefing!,
      tldr: { text: top.map((card) => card.statement.replace(/\.$/, "")).join("; ") + ".", references: top.map((_, index) => index + 1) },
      sections: [{ heading: "This week", paragraphs: top.map((card, index) => ({ text: card.statement, references: [index + 1] })) }],
      citations: top.map((card, index) => ({ number: index + 1, title: card.title, url: card.url })) },
  });
  window.history.replaceState(null, "", "/");
  createRoot(root).render(<App auth={auth} research={research} radar={radar} catalog={{
    recent: async () => page(items.slice(0, 20)),
    search: async (query) => page(items.filter((item) => !query
      || `${item.title} ${item.summary}`.toLowerCase().includes(query.toLowerCase())).slice(0, 20)),
    sources: async () => sourceCatalog,
    detail: async (id) => ({ ...newsDetail, ...items.find((item) => item.id === id) }),
    briefing: mockBriefing,
  }} />);
}
