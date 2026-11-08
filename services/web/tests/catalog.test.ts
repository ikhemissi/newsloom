// @vitest-environment node
import { spawn } from "node:child_process";
import { once } from "node:events";
import { fileURLToPath } from "node:url";
import { afterAll, beforeAll, expect, test, vi } from "vitest";
import { z } from "zod";
import { HttpCatalog, validateSearch } from "../src/catalog";
import type { AuthSession } from "../src/domain";
import { runtimeConfig } from "./fixtures";

const root = fileURLToPath(new URL("../../../", import.meta.url));
const child = spawn("uv", ["run", "--directory", root, "--locked", "python",
  "services/web/tests/http_fixture.py"], { cwd: root, stdio: ["ignore", "pipe", "ignore"] });
let endpoint = "";
beforeAll(async () => {
  if (child.exitCode !== null) throw new Error("authored_http_fixture_startup");
  const [data] = await Promise.race([
    once(child.stdout, "data"),
    once(child, "exit").then(() => { throw new Error("authored_http_fixture_startup"); }),
  ]);
  endpoint = `http://127.0.0.1:${z.object({ port: z.number() }).parse(JSON.parse(String(data))).port}/api/v1`;
}, 10000);
afterAll(async () => {
  child.kill("SIGTERM");
  if (child.exitCode === null) await once(child, "exit");
});
const auth: AuthSession = {
  signedIn: () => true, signIn: async () => undefined, signOut: async () => undefined,
  token: vi.fn(async () => "fixture-news-token"),
};
const signal = () => new AbortController().signal;
const catalog = (fetchImpl: typeof fetch = fetch) => new HttpCatalog({ ...runtimeConfig, newsApiUrl: endpoint }, auth, fetchImpl);

test("the browser interoperates with the actual HTTP API without MCP or A2A requests", async () => {
  const paths: string[] = [];
  const client = catalog(async (input, options) => {
    const url = new URL(String(input));
    paths.push(url.pathname);
    expect(url.pathname.startsWith("/api/v1/")).toBe(true);
    expect(new Headers(options?.headers).get("Authorization")).toBe("Bearer fixture-news-token");
    expect(options?.credentials).toBe("omit");
    expect(options?.redirect).toBe("error");
    expect(options?.cache).toBe("no-store");
    if (url.pathname.endsWith("/search")) expect(JSON.parse(String(options?.body))).toEqual({ query: "fixture query", limit: 20 });
    return fetch(input, options);
  });
  const recent = await client.recent(signal());
  expect(recent.items[0]?.title).toBe("Authored SDK result");
  expect((await client.search("fixture query", signal())).items[0]?.summary).toBe("Authored summary.");
  expect((await client.sources(signal())).categories[0]?.id).toBe("agents-applications");
  const id = recent.items[0]?.id;
  expect(id).toBeDefined();
  if (id) expect((await client.detail(id, signal()))?.dateOrigin).toBe("published");
  expect(await client.detail(crypto.randomUUID(), signal())).toBeNull();
  expect(paths).toHaveLength(5);
  expect(auth.token).toHaveBeenCalledWith("news");
});

test("metadata-only filters omit the query, keep boundaries and preserve empty results", async () => {
  const client = catalog();
  const filters = { source: "fixture-source", category: "agents-applications",
    from: "2026-11-01T08:00:00Z", to: "2026-11-01T09:00:00Z" };
  expect((await client.search(undefined, signal(), filters)).items).toHaveLength(1);
  expect((await client.search(undefined, signal(), { ...filters, category: "models" })).items).toEqual([]);
  expect((await client.search(undefined, signal(), { ...filters, from: "2026-11-01T07:00:00Z", to: "2026-11-01T08:00:00Z" })).items).toEqual([]);
  expect((await client.search("empty", signal())).items).toEqual([]);
  expect(validateSearch("a".repeat(2048)).length).toBe(2048);
  expect(() => validateSearch("a".repeat(2049))).toThrow("invalid_search");
});

test("malformed API envelopes, cursor authority and out-of-scope records fail explicitly", async () => {
  const base = (await catalog().recent(signal()));
  const item = base.items[0];
  if (!item) throw new Error("fixture_item_missing");
  const wireItem = { ...item, published_at: item.publishedAt, tags: [] };
  const meta = { read_at: base.readAt, cache_age_seconds: 0, result_scope: "page" };
  for (const body of [
    {}, { items: [wireItem, wireItem], next_cursor: null, meta },
    { items: [], next_cursor: "https://attacker.test", meta },
    { items: [{ ...wireItem, source: "other-source" }], next_cursor: null, meta },
    { items: [wireItem], next_cursor: null, meta: { ...meta, result_scope: "bounded" } },
    { items: [wireItem], next_cursor: null, meta: { ...meta, cache_age_seconds: -1 } },
    { items: [wireItem], next_cursor: null, meta: { ...meta, read_at: "2026-11-03T00:00:00" } },
    ...["not-a-date", "2026-11-03T00:00:00"].map((published_at) => ({
      items: [{ ...wireItem, published_at }], next_cursor: null, meta,
    })),
    { items: Array.from({ length: 21 }, () => ({ ...wireItem, id: crypto.randomUUID() })), next_cursor: null, meta },
  ]) {
    await expect(catalog(async () => Response.json(body)).search(undefined, signal(), { source: "fixture-source" }))
      .rejects.toThrow("invalid_response");
  }
  await expect(catalog().search(undefined, signal(), {}, "https://attacker.test")).rejects.toThrow("invalid_news_request");
});

test("HTTP failures, oversized bodies and cancellation cannot become successful empty data", async () => {
  for (const [status, category] of [[400, "invalid_news_request"], [401, "authorization"],
    [403, "authorization"], [413, "invalid_news_request"], [429, "overloaded"], [504, "timeout"]] as const) {
    const request = vi.fn(async () => Response.json({ error: "PRIVATE_CANARY" }, { status }));
    await expect(catalog(request).recent(signal())).rejects.toMatchObject({ category });
    expect(request).toHaveBeenCalledOnce();
  }
  await expect(catalog(async () => Response.json({ items: "x".repeat(1048577) })).recent(signal()))
    .rejects.toThrow("invalid_response");
  const controller = new AbortController();
  const pending = catalog().search("delay", controller.signal);
  const assertion = expect(pending).rejects.toThrow();
  setTimeout(() => controller.abort(), 50);
  await assertion;
});

test("stored microsecond ordering is preserved and uncached read ages above TTL remain valid", async () => {
  const ids = [crypto.randomUUID(), crypto.randomUUID()].sort();
  const rows = ids.reverse().map((id, index) => ({
    id, title: "Authored", summary: "Authored", source: "fixture-source",
    category: "models", tags: [], url: "https://publisher.test/article",
    published_at: index === 0 ? "2026-11-01T08:00:00.000900Z" : "2026-11-01T08:00:00.000100Z",
  }));
  const result = await catalog(async () => Response.json({
    items: rows, next_cursor: null,
    meta: { read_at: "2026-11-01T08:00:00Z", cache_age_seconds: 61, result_scope: "page" },
  })).recent(signal());
  expect(result.items.map((item) => item.id)).toEqual(ids);
  expect(result.cacheAgeSeconds).toBe(61);
});

test("detail maps stored announcements and treats older items as having none", async () => {
  const announcement = { statement: "Widget reached GA.", change_type: "launch", status: "ga",
    effective_date: "2026-11-02", deadline: null, products: ["Widget"] };
  let inject = true;
  const client = catalog(async (input, options) => {
    const response = await fetch(input, options);
    if (!new URL(String(input)).pathname.includes("/news/")) return response;
    const body = await response.json() as { item: Record<string, unknown> };
    if (inject) body.item.announcements = [announcement];
    return new Response(JSON.stringify(body), { status: 200, headers: response.headers });
  });
  const id = (await client.recent(signal())).items[0]?.id ?? "";
  expect((await client.detail(id, signal()))?.announcements).toEqual([{ statement: "Widget reached GA.",
    status: "ga", effectiveDate: "2026-11-02", deadline: null, products: ["Widget"] }]);
  inject = false;
  expect((await client.detail(id, signal()))?.announcements).toEqual([]);
});
