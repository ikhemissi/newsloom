// @vitest-environment node
import { expect, test, vi } from "vitest";
import type { AuthSession } from "../src/domain";
import { HttpRadar } from "../src/radarClient";
import { runtimeConfig } from "./fixtures";

const auth: AuthSession = {
  signedIn: () => true, signIn: async () => undefined, signOut: async () => undefined,
  token: vi.fn(async () => "fixture-news-token"),
};
const signal = () => new AbortController().signal;
const id = () => crypto.randomUUID();
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), {
  status, headers: { "Content-Type": "application/json" },
});
const card = (statement: string, tier = "act_now") => ({
  id: id(), news_id: id(), title: "Item", url: "https://publisher.test/a", source: "fixture",
  published_at: "2026-11-07T10:00:00+00:00", article_kind: "security", statement, status: "ga",
  effective_date: null, deadline: "2026-12-01", products: [{ id: id(), name: "Widget", vendor: "Acme", vendor_id: id() }],
  tier, reason: "Matters.", capability: "security", in_stack: true, state: null,
});

test("radar responses map to the page model and writes use PUT with JSON", async () => {
  const calls: { url: string; method: string; body: unknown }[] = [];
  const fetchImpl = vi.fn(async (input: RequestInfo | URL, options?: RequestInit) => {
    calls.push({ url: String(input), method: options?.method ?? "GET",
      body: options?.body ? JSON.parse(String(options.body)) : null });
    expect(options?.credentials).toBe("omit");
    expect(new Headers(options?.headers).get("Authorization")).toBe("Bearer fixture-news-token");
    const url = String(input);
    if (url.includes("/radar")) return json({ window: 30, deadlines: [], hidden: [],
      tiers: { act_now: [{ kind: "card", card: card("Patch now.") }],
        worth_knowing: [{ kind: "group", capability: "agent tools", cards: [card("A.", "worth_knowing"), card("B.", "worth_knowing")] }],
        later: [] } });
    if (url.includes("/me/cards/")) return json({ state: "done" });
    if (url.endsWith("/products/" + missing)) return json({ error: { code: "not_found", request_id: "x" } }, 404);
    return json({ items: [{ id: id(), name: "Acme", kind: "vendor", vendor: null }] });
  }) as typeof fetch;
  const missing = id();
  const client = new HttpRadar(runtimeConfig, auth, fetchImpl);
  const radar = await client.radar(30, signal());
  expect(radar.tiers.act_now[0]).toMatchObject({ kind: "card", card: { statement: "Patch now.", inStack: true, deadline: "2026-12-01" } });
  expect(radar.tiers.worth_knowing[0]?.kind).toBe("group");
  const announcement = id();
  await client.setCard(announcement.toUpperCase(), "done", signal());
  expect((await client.setStack([announcement], signal()))[0]?.name).toBe("Acme");
  expect(await client.product(missing, signal())).toBeNull();
  expect(calls.map((call) => [call.method, call.url.replace(runtimeConfig.newsApiUrl, "")])).toEqual([
    ["GET", "/radar?window=30"], ["PUT", `/me/cards/${announcement}`], ["PUT", "/me/stack"], ["GET", `/products/${missing}`],
  ]);
  expect(calls[1]?.body).toEqual({ state: "done" });
  expect(calls[2]?.body).toEqual({ ids: [announcement] });
});

test("invalid identifiers and responses fail without leaking validation details", async () => {
  const client = new HttpRadar(runtimeConfig, auth, (async () => json({ window: 7, tiers: {} })) as typeof fetch);
  await expect(client.radar(7, signal())).rejects.toMatchObject({ category: "invalid_response" });
  await expect(client.product("not-a-uuid", signal())).rejects.toMatchObject({ category: "invalid_news_request" });
  const denied = new HttpRadar(runtimeConfig, auth, (async () => json({}, 403)) as typeof fetch);
  await expect(denied.stack(signal())).rejects.toMatchObject({ category: "authorization" });
});
