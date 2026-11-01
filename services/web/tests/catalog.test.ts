// @vitest-environment node
import { spawn } from "node:child_process";
import { once } from "node:events";
import { fileURLToPath } from "node:url";
import { afterAll, beforeAll, expect, test, vi } from "vitest";
import { z } from "zod";
import { McpCatalog, validateSearch } from "../src/catalog";
import { UiFailure } from "../src/domain";
import type { AuthSession } from "../src/domain";
import { runtimeConfig } from "./fixtures";

const root = fileURLToPath(new URL("../../../", import.meta.url));
const child = spawn("uv", ["run", "--directory", root, "--locked", "python",
  "services/web/tests/mcp_fixture.py"], { cwd: root, stdio: ["ignore", "pipe", "ignore"] });
let endpoint = "";
beforeAll(async () => {
  if (child.exitCode !== null) throw new Error("authored_mcp_fixture_startup");
  const [data] = await Promise.race([
    once(child.stdout, "data"),
    once(child, "exit").then(() => { throw new Error("authored_mcp_fixture_startup"); }),
  ]);
  const value = z.object({ port: z.number() }).parse(JSON.parse(String(data)));
  endpoint = `http://127.0.0.1:${value.port}/mcp`;
}, 10000);
afterAll(async () => {
  child.kill("SIGTERM");
  if (child.exitCode === null) await once(child, "exit");
});
const auth: AuthSession = {
  signedIn: () => true, signIn: async () => undefined, signOut: async () => undefined,
  token: vi.fn(async () => "fixture-news-token"),
};

test("official modern client interoperates with the current Python server and never invokes A2A", async () => {
  const methods: string[] = [];
  const observedFetch: typeof fetch = async (input, options) => {
    const request = z.object({ method: z.string() }).parse(JSON.parse(String(options?.body)));
    methods.push(request.method);
    expect(new Headers(options?.headers).get("Mcp-Method")).toBe(request.method);
    expect(new Headers(options?.headers).get("MCP-Protocol-Version")).toBe("2026-07-28");
    const params = z.object({
      params: z.object({ _meta: z.record(z.string(), z.unknown()) }).passthrough(),
    }).parse(JSON.parse(String(options?.body))).params;
    expect(params._meta["io.modelcontextprotocol/protocolVersion"]).toBe("2026-07-28");
    if (request.method === "tools/call") {
      expect(new Headers(options?.headers).get("Mcp-Name")).toMatch(/^(get_recent_news|search_news)$/);
    }
    expect(String(input)).toBe(endpoint);
    return fetch(input, options);
  };
  const catalog = new McpCatalog({ ...runtimeConfig, mcpUrl: endpoint }, auth, observedFetch);
  expect((await catalog.recent(new AbortController().signal))[0]?.title).toBe("Authored SDK result");
  expect((await catalog.search("fixture query", new AbortController().signal))[0]?.summary).toBe("Authored summary.");
  expect(methods).not.toContain("initialize");
  expect(methods).not.toContain("SendStreamingMessage");
  expect(methods.filter((method) => method === "tools/call")).toHaveLength(2);
  expect(auth.token).toHaveBeenCalledWith("news");
});

test("empty search is valid, cancellation terminates real HTTP work and limits are exact", async () => {
  const catalog = new McpCatalog({ ...runtimeConfig, mcpUrl: endpoint }, auth);
  expect(await catalog.search("empty", new AbortController().signal)).toEqual([]);
  const controller = new AbortController();
  const result = catalog.search("delay", controller.signal);
  const assertion = expect(result).rejects.toThrow();
  setTimeout(() => controller.abort(), 50);
  await assertion;
  expect(validateSearch("a".repeat(2048)).length).toBe(2048);
  expect(validateSearch("\u{1F600}".repeat(2048)).length).toBe(4096);
  expect(() => validateSearch("a".repeat(2049))).toThrow("invalid_search");
});

test("malformed, duplicate or oversized result sets never become successful empty news", async () => {
  const item = {
    id: crypto.randomUUID(), title: "Authored", summary: "Authored", source: "fixture",
    category: "agents", tags: [], published_at: "2026-11-01T08:00:00Z",
    url: "https://publisher.test/article",
  };
  for (const structuredContent of [
    {}, { items: [{ ...item, published_at: "not-a-date" }] },
    { items: [item, { ...item, id: item.id.toUpperCase() }] },
    { items: Array.from({ length: 21 }, () => ({ ...item, id: crypto.randomUUID() })) },
  ]) {
    const fetchImpl: typeof fetch = async (input, options) => {
      const response = await fetch(input, options);
      const request = z.object({ method: z.string() }).parse(JSON.parse(String(options?.body)));
      if (request.method !== "tools/call") return response;
      const data = z.record(z.string(), z.unknown()).parse(await response.json());
      const result = z.record(z.string(), z.unknown()).parse(data.result);
      return Response.json({ ...data, result: { ...result, content: [], structuredContent } });
    };
    const catalog = new McpCatalog({ ...runtimeConfig, mcpUrl: endpoint }, auth, fetchImpl);
    await expect(catalog.recent(new AbortController().signal)).rejects.toBeInstanceOf(UiFailure);
  }
});

test("real SDK discovery and filtered searches preserve IDs, predicates and query-less boundaries", async () => {
  const calls: { name: string; arguments: Record<string, unknown> }[] = [];
  const fetchImpl: typeof fetch = async (input, options) => {
    const request = JSON.parse(String(options?.body));
    if (request.method === "tools/call") calls.push(request.params);
    return fetch(input, options);
  };
  const catalog = new McpCatalog({ ...runtimeConfig, mcpUrl: endpoint }, auth, fetchImpl);
  const [sources, recent] = await Promise.all([
    catalog.sources(new AbortController().signal), catalog.recent(new AbortController().signal),
  ]);
  expect(sources.sources[0]).toEqual({ id: "fixture-source", categories: ["agents-applications"] });
  expect(sources.categories[0]?.label).toBe("Agents and applications");
  expect(recent).toHaveLength(1);
  const filters = { source: "fixture-source", category: "agents-applications",
    from: "2026-11-01T08:00:00Z", to: "2026-11-01T09:00:00Z" };
  expect(await catalog.search(undefined, new AbortController().signal, filters)).toHaveLength(1);
  expect(calls.at(-1)?.arguments).toEqual({ ...filters, limit: 20 });
  expect(calls.at(-1)?.arguments).not.toHaveProperty("query");
  expect(await catalog.search("fixture", new AbortController().signal, filters)).toHaveLength(1);
  expect(calls.at(-1)?.arguments).toEqual({ ...filters, query: "fixture", limit: 20 });
  expect(await catalog.search(undefined, new AbortController().signal, {
    ...filters, from: "2026-11-01T07:00:00Z", to: "2026-11-01T08:00:00Z",
  })).toEqual([]);
  expect(await catalog.search(undefined, new AbortController().signal, { ...filters, category: "models" })).toEqual([]);
});

test("catalogue validation, authorization and abort failures are explicit", async () => {
  for (const structuredContent of [
    {}, { sources: [], categories: [{ id: "models", label: "" }] },
    { sources: [{ id: "fixture-source", categories: ["unknown"] }], categories: [] },
    { sources: [], categories: [{ id: "models", label: "Models" }, { id: "models", label: "Duplicate" }] },
  ]) {
    const catalog = new McpCatalog({ ...runtimeConfig, mcpUrl: endpoint }, auth, async (input, options) => {
      const response = await fetch(input, options);
      if (JSON.parse(String(options?.body)).method !== "tools/call") return response;
      const data = await response.json();
      return Response.json({ ...data, result: { ...data.result, content: [], structuredContent } });
    });

    await expect(catalog.sources(new AbortController().signal)).rejects.toBeInstanceOf(UiFailure);
  }
  const denied = new McpCatalog({ ...runtimeConfig, mcpUrl: endpoint }, { ...auth, token: async () => "denied" });
  await expect(denied.sources(new AbortController().signal)).rejects.toMatchObject({ category: "authorization" });
  const controller = new AbortController();
  controller.abort();
  await expect(new McpCatalog({ ...runtimeConfig, mcpUrl: endpoint }, auth).sources(controller.signal)).rejects.toThrow("timeout");
});

test("valid protocol responses outside the requested metadata scope are rejected rather than filtered or broadened", async () => {
  const catalog = new McpCatalog({ ...runtimeConfig, mcpUrl: endpoint }, auth, async (input, options) => {
    const response = await fetch(input, options);
    if (JSON.parse(String(options?.body)).method !== "tools/call") return response;
    const data = await response.json();
    return Response.json({ ...data, result: { ...data.result, structuredContent: {
      items: [{
        id: crypto.randomUUID(), title: "Authored", summary: "Authored", source: "different-source",
        category: "models", tags: [], published_at: "2026-11-01T08:00:00Z", similarity: null,
        url: "https://publisher.test/article",
      }],
    } } });
  });
  await expect(catalog.search(undefined, new AbortController().signal, {
    source: "fixture-source", category: "agents-applications",
  })).rejects.toThrow("invalid_response");
});
