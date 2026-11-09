import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { expect, test } from "vitest";
import { ProductPage, RadarPage, StackPage } from "../src/Radar";
import { entryCards } from "../src/radar";
import type { FixtureCard } from "./radar-fixture";
import { FixtureRadar } from "./radar-fixture";

const NOW = new Date("2026-11-08T12:00:00Z");
function card(id: string, overrides: Partial<FixtureCard> = {}): FixtureCard {
  return {
    id, news_id: `https://publisher.test/${id}`, title: `Item ${id}`, url: `https://publisher.test/${id}`,
    source: "fixture", published_at: "2026-11-07T10:00:00Z", article_kind: "announcement",
    statement: `Statement ${id}.`, status: "ga", effective_date: null, deadline: null,
    products: [{ name: `Product ${id}`, vendor: "Acme" }], tier: "worth_knowing",
    reason: `Reason ${id}.`, capability: "other", ...overrides,
  };
}
const navigate = () => undefined;

test("stack keeps act now for followed products, security and regulation only", async () => {
  const radar = new FixtureRadar([
    card("a", { tier: "act_now" }),
    card("b", { tier: "act_now", products: [{ name: "Gateway", vendor: "Other" }] }),
    card("c", { tier: "act_now", article_kind: "security", products: [{ name: "Proxy", vendor: "Other" }] }),
  ], () => NOW);
  expect((await radar.radar(7)).tiers.act_now).toHaveLength(3);
  const acme = (await radar.search("Acme"))[0]!;
  await radar.setStack([acme.id]);
  const ranked = await radar.radar(7);
  expect(ranked.tiers.act_now.flatMap(entryCards).map((item) => item.statement)).toEqual(["Statement a.", "Statement c."]);
  expect(ranked.tiers.worth_knowing.flatMap(entryCards).map((item) => item.statement)).toEqual(["Statement b."]);
});

test("same capability groups only across vendors; windows, snooze and deadlines apply", async () => {
  const radar = new FixtureRadar([
    card("a", { capability: "browser automation" }),
    card("b", { capability: "browser automation", products: [{ name: "Browser", vendor: "Other" }] }),
    card("c", { capability: "agent memory" }),
    card("d", { published_at: "2026-10-20T00:00:00Z" }),
    card("e", { deadline: "2026-12-01" }),
    card("f", { tier: "later", deadline: "2026-11-20" }),
  ], () => NOW);
  const week = await radar.radar(7);
  expect(week.tiers.worth_knowing.map((entry) => entry.kind)).toEqual(["card", "group", "card"]);
  expect(week.tiers.worth_knowing.flatMap(entryCards)).toHaveLength(4);
  expect(week.deadlines.map((item) => item.statement)).toEqual(["Statement e."]);
  expect((await radar.radar(30)).tiers.worth_knowing.flatMap(entryCards)).toHaveLength(5);
  const [first] = week.tiers.worth_knowing.flatMap(entryCards);
  await radar.setCard(first!.id, "snoozed");
  const snoozed = await radar.radar(7);
  expect(snoozed.hidden.map((item) => item.state)).toEqual(["snoozed"]);
  const later = new FixtureRadar([card("a")], () => new Date(NOW.getTime() + 8 * 86_400_000));
  expect((await later.radar(30)).hidden).toEqual([]);
});

test("radar page shows tiers, hides done cards, follows products and asks with the item", async () => {
  const radar = new FixtureRadar([card("a", { tier: "act_now" }), card("b"), card("c", { tier: "later" })], () => NOW);
  const asked: string[] = [];
  render(<RadarPage client={radar} navigate={navigate} now={NOW} briefing={<p>Authored briefing</p>}
    onAsk={(item) => asked.push(item.title)} />);
  const act = await screen.findByRole("heading", { name: "Act now · 1" });
  expect(act).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Worth knowing · 1" })).toBeInTheDocument();
  expect(screen.getByText("Why: Reason a.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Ask about this: Statement a." }));
  expect(asked).toEqual(["Item a"]);
  fireEvent.click(screen.getByRole("button", { name: "Done: Statement a." }));
  await screen.findByRole("heading", { name: "Act now · 0" });
  fireEvent.click(await screen.findByRole("button", { name: "Hidden (1)" }));
  fireEvent.click(within(screen.getByRole("region", { name: "Hidden" })).getByRole("button", { name: "Restore: Statement a." }));
  await screen.findByRole("heading", { name: "Act now · 1" });
  expect(screen.getByRole("link", { name: /Statement a\./ })).toHaveAttribute("rel", "noopener noreferrer");
  // Following another vendor's product demotes this act-now item, as the stack rules require.
  fireEvent.click(screen.getByRole("button", { name: "Follow products: Statement b." }));
  await screen.findByRole("heading", { name: "Act now · 0" });
  expect((await radar.stack()).map((entry) => entry.name)).toEqual(["Product b"]);
});

test("product page shows the timeline and toggles following", async () => {
  const radar = new FixtureRadar([card("a"), card("b", { products: [{ name: "Product a", vendor: "Acme" }] })], () => NOW);
  const product = (await radar.search("Product a")).find((entry) => entry.kind === "product")!;
  render(<ProductPage client={radar} id={product.id} navigate={navigate} onBack={() => undefined} />);
  expect(await screen.findByRole("heading", { name: "Product a" })).toBeInTheDocument();
  expect(screen.getAllByRole("listitem")).toHaveLength(2);
  fireEvent.click(screen.getByRole("button", { name: "☆ Follow" }));
  expect(await screen.findByRole("button", { name: "★ Following" })).toHaveAttribute("aria-pressed", "true");
  expect(await radar.product(crypto.randomUUID())).toBeNull();
});

test("stack page adds and removes vendors and products", async () => {
  const radar = new FixtureRadar([card("a")], () => NOW);
  render(<StackPage client={radar} navigate={navigate} />);
  fireEvent.change(screen.getByRole("searchbox"), { target: { value: "ac" } });
  fireEvent.click(await screen.findByRole("button", { name: "+ Acme" }));
  const chips = await screen.findByRole("list", { name: "Followed" });
  await waitFor(() => expect(within(chips).getByText("Acme")).toBeInTheDocument());
  fireEvent.click(within(chips).getByRole("button", { name: "Remove Acme" }));
  await waitFor(() => expect(within(chips).queryByText("Acme")).toBeNull());
});
