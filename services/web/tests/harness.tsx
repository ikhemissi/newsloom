import { createRoot } from "react-dom/client";
import { App } from "../src/App";
import { parseAnswer } from "../src/answer";
import type { AuthSession, ResearchClient } from "../src/domain";
import { newsItem } from "./fixtures";
import "../src/style.css";

document.documentElement.dataset.researchCalls = "0";
document.documentElement.dataset.searchCalls = "0";

const auth: AuthSession = {
  signedIn: () => true, signIn: async () => undefined, signOut: async () => undefined,
  token: async () => { throw new Error("Authored harness never acquires tokens"); },
};
const research: ResearchClient = {
  async *ask() {
    document.documentElement.dataset.researchCalls = String(
      Number(document.documentElement.dataset.researchCalls) + 1,
    );
    yield { kind: "progress", phase: "retrieving" };
    const paragraphs = new URLSearchParams(location.search).has("long")
      ? Array.from({ length: 60 }, (_, index) =>
        `Authored long paragraph ${index + 1}. This fixture checks independent panel scrolling without live research.`).join("\n\n")
      : "<img src=x onerror=bad()> [1]";
    yield { kind: "answer", answer: parseAnswer(
      `${paragraphs}\n\nLimitation: authored UI fixture only.\n\n[1] https://publisher.test/article`,
    ) };
  },
  stop: async () => false,
};
const container = document.getElementById("root");
if (!container) throw new Error("Missing fixture root");
createRoot(container).render(<App auth={auth} research={research} catalog={{
  recent: async () => [newsItem],
  search: async () => {
    document.documentElement.dataset.searchCalls = String(
      Number(document.documentElement.dataset.searchCalls) + 1,
    );
    return [{ ...newsItem, title: "Authored search result" }];
  },
}} />);
