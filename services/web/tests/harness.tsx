import { createRoot } from "react-dom/client";
import { App } from "../src/App";
import { parseAnswer } from "../src/answer";
import type { AuthSession, ResearchClient } from "../src/domain";
import { UiFailure } from "../src/domain";
import { newsItem, sourceCatalog, newsDetail, page } from "./fixtures";
import { matchesFilters } from "../src/filters";
import "../src/style.css";

document.documentElement.dataset.researchCalls = "0";
document.documentElement.dataset.searchCalls = "0";
document.documentElement.dataset.querylessCalls = "0";
const parameters = new URLSearchParams(location.search);
window.history.replaceState(null, "", parameters.get("route")
  ?? (location.pathname.startsWith("/news/") ? location.pathname : "/"));
let catalogueAttempts = 0;

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
    const paragraphs = parameters.has("long")
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
function batch(cursor?: string) {
  const start = Number(cursor?.replace("page_", "") ?? 0);
  return page(Array.from({ length: 20 }, (_, offset) => ({
    ...newsItem, id: newsItem.id.slice(0, 24) + String(start + offset).padStart(12, "0"),
    title: `Authored page item ${start + offset + 1}`,
  })), start + 20 < 240 ? `page_${start + 20}` : null);
}
createRoot(container).render(<App auth={auth} research={research} catalog={{
  recent: async () => parameters.has("paged") ? batch() : page([newsItem]),
  detail: async (id) => parameters.has("missing") ? null : ({ ...newsDetail, id }),
  sources: async () => {
    catalogueAttempts++;
    if (parameters.has("catalogue-error") && catalogueAttempts === 1) throw new UiFailure("unavailable");
    return parameters.has("hostile-catalogue") ? {
      ...sourceCatalog, categories: sourceCatalog.categories.map((category) => ({
        ...category, label: "<svg onload=bad()>",
      })),
    } : sourceCatalog;
  },
  search: async (_query, _signal, filters = {}, cursor) => {
    document.documentElement.dataset.searchCalls = String(
      Number(document.documentElement.dataset.searchCalls) + 1,
    );
    if (_query === undefined) document.documentElement.dataset.querylessCalls = String(
      Number(document.documentElement.dataset.querylessCalls) + 1,
    );
    if (parameters.has("paged") && _query === undefined) return batch(cursor);
    return page([{ ...newsItem, title: "Authored search result" }].filter((item) => matchesFilters(item, filters)));
  },
}} />);
