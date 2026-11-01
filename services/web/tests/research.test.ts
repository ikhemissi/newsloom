import { expect, test, vi } from "vitest";
import { A2aResearch, guardedFetch } from "../src/research";
import { runtimeConfig } from "./fixtures";
import type { AuthSession } from "../src/domain";

export const config = runtimeConfig;
export const card = {
  name: "Fixture", version: "1", capabilities: { streaming: true },
  supportedInterfaces: [{ url: config.agentUrl, protocolBinding: "JSONRPC", protocolVersion: "1.0" }],
  defaultInputModes: ["text/plain", "application/json"], defaultOutputModes: ["text/plain"],
  skills: [{ id: "research" }],
  securitySchemes: { entra: { oauth2SecurityScheme: { flows: {
    authorizationCode: { scopes: { [config.agentScope]: "research" }, pkceRequired: true },
  } } } },
  securityRequirements: [{ schemes: { entra: { list: [config.agentScope] } } }],
};
const auth: AuthSession = {
  signedIn: () => true, signIn: async () => undefined, signOut: async () => undefined,
  token: async () => "authored-fixture-token",
};
const ids = { taskId: "fixture-task", contextId: "fixture-context" };
const text = "Fixture claim [1]\n\nLimitation: summaries only.\n\n[1] https://publisher.test/article";
const artifact = { artifactId: "fixture-answer", parts: [{ text }] };
const finalTask = { id: ids.taskId, contextId: ids.contextId,
  status: { state: "TASK_STATE_COMPLETED" }, artifacts: [artifact] };

export function fixtureEvents() {
  return [
    { task: { id: ids.taskId, contextId: ids.contextId, status: { state: "TASK_STATE_SUBMITTED" } } },
    { statusUpdate: { ...ids, status: { state: "TASK_STATE_WORKING", message: { parts: [
      { text: JSON.stringify({ phase: "retrieving", tool_calls: 0, evidence_items: 0 }) },
    ] } } } },
    { artifactUpdate: { ...ids, artifact, lastChunk: true } },
    { statusUpdate: { ...ids, status: { state: "TASK_STATE_COMPLETED" } } },
    { task: finalTask },
  ];
}

function transport(events = fixtureEvents(), calls: string[] = []): typeof fetch {
  return async (input, options) => {
    if (String(input).endsWith("/.well-known/agent-card.json")) {
      expect(new Headers(options?.headers).has("Authorization")).toBe(false);
      return Response.json(card);
    }
    expect(new Headers(options?.headers).get("Authorization")).toBe("Bearer authored-fixture-token");
    const request: { method: string; id: number } = JSON.parse(String(options?.body));
    calls.push(request.method);
    if (request.method === "CancelTask")
      return Response.json({ jsonrpc: "2.0", id: request.id, result: {
        ...finalTask, status: { state: "TASK_STATE_CANCELED" },
      } });
    expect(request.method).toBe("SendStreamingMessage");
    return new Response(events.map((result) =>
      `data: ${JSON.stringify({ jsonrpc: "2.0", id: request.id, result })}\n\n`).join(""), {
      headers: { "Content-Type": "text/event-stream" },
    });
  };
}

test("real SDK adapter handles completion status then final task without extra successful readbacks", async () => {
  const calls: string[] = [];
  const adapter = new A2aResearch(config, auth, transport(fixtureEvents(), calls));
  const events = [];
  for await (const event of adapter.ask("Fixture question", new AbortController().signal)) events.push(event);
  expect(events.map((event) => event.kind)).toEqual(["progress", "answer"]);
  expect(calls).toEqual(["SendStreamingMessage"]);
});

test("truncated or mismatched final answers cannot become success", async () => {
  for (const events of [
    fixtureEvents().slice(0, -1),
    [...fixtureEvents().slice(0, -1), { task: { ...finalTask, artifacts: [] } }],
  ]) {
    const adapter = new A2aResearch(config, auth, transport(events));
    await expect(async () => { for await (const event of adapter.ask("Fixture", new AbortController().signal)) void event; })
      .rejects.toThrow("invalid_response");
  }
});

test("discovery drift rejects before acquiring or disclosing a bearer token", async () => {
  const token = vi.fn(auth.token);
  const adapter = new A2aResearch(config, { ...auth, token }, async () =>
    Response.json({ ...card, supportedInterfaces: [{ url: "https://other.test/a2a", protocolBinding: "JSONRPC", protocolVersion: "1.0" }] }));
  await expect(async () => { for await (const event of adapter.ask("Fixture", new AbortController().signal)) void event; })
    .rejects.toThrow("invalid_response");
  expect(token).not.toHaveBeenCalled();
});

test("stop uses a new bounded cancellation transport, not the aborted streaming signal", async () => {
  const calls: string[] = [];
  const adapter = new A2aResearch(config, auth, transport(fixtureEvents(), calls));
  const stream = adapter.ask("Fixture", new AbortController().signal)[Symbol.asyncIterator]();
  expect((await stream.next()).value.kind).toBe("progress");
  expect(await adapter.stop()).toBe(true);
  await stream.return?.();
  expect(calls).toEqual(["SendStreamingMessage", "CancelTask"]);
});

test("raw transport limit accepts exactly 1 MiB and rejects excess before SDK buffering", async () => {
  for (const length of [1048576, 1048577]) {
    const guarded = guardedFetch(config.agentUrl, null, new AbortController().signal,
      async () => new Response("a".repeat(length)));
    const response = await guarded(config.agentUrl);
    if (length === 1048576) expect((await response.text()).length).toBe(length);
    else await expect(response.text()).rejects.toThrow("invalid_response");
  }
});

test("HTTP failures are explicit and cannot replay a research POST", async () => {
  for (const [status, category] of [[401, "authorization"], [403, "authorization"],
    [429, "overloaded"], [504, "timeout"]] as const) {
    const request = vi.fn(async () => new Response("PRIVATE_ERROR_CANARY", { status }));
    const guarded = guardedFetch(config.agentUrl, "fixture", new AbortController().signal, request);
    await expect(guarded(config.agentUrl, { method: "POST" })).rejects.toMatchObject({ category });
    expect(request).toHaveBeenCalledOnce();
  }
});

test("one in-flight request is enforced without dispatching a second question", async () => {
  const calls: string[] = [];
  const adapter = new A2aResearch(config, auth, transport(fixtureEvents(), calls));
  const stream = adapter.ask("Fixture", new AbortController().signal)[Symbol.asyncIterator]();
  await stream.next();
  await expect(async () => {
    for await (const event of adapter.ask("Second fixture", new AbortController().signal)) void event;
  }).rejects.toThrow("overloaded");
  expect(calls).toEqual(["SendStreamingMessage"]);
  await stream.return?.();
});

test("the whole request deadline aborts pending discovery at 120 seconds", async () => {
  vi.useFakeTimers();
  try {
    const adapter = new A2aResearch(config, auth, async (_, options) =>
      new Promise<Response>((_, reject) => {
        options?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true });
      }));
    const result = (async () => {
      for await (const event of adapter.ask("Fixture", new AbortController().signal)) void event;
    })();
    const assertion = expect(result).rejects.toThrow("timeout");
    await vi.advanceTimersByTimeAsync(119999);
    expect(vi.getTimerCount()).toBe(1);
    await vi.advanceTimersByTimeAsync(1);
    await assertion;
    expect(vi.getTimerCount()).toBe(0);
  } finally { vi.useRealTimers(); }
});

test("selected-news IDs reach the existing A2A data contract exactly", async () => {
  const selected = crypto.randomUUID();
  const base = transport();
  const fetchImpl: typeof fetch = async (input, options) => {
    if (String(input).endsWith("/a2a")) {
      const request = JSON.parse(String(options?.body));
      expect(request.params.message.parts[0].data.item_ids).toEqual([selected]);
    }
    return base(input, options);
  };
  const adapter = new A2aResearch(config, auth, fetchImpl);
  for await (const event of adapter.ask("Fixture", new AbortController().signal, [selected])) void event;
  await expect(async () => {
    for await (const event of adapter.ask("Fixture", new AbortController().signal, [selected, selected])) void event;
  }).rejects.toThrow("invalid_input");
});

test("A2A filters are validated structured fields frozen before asynchronous transport", async () => {
  const filters = { source: "fixture-source", category: "agents-applications",
    from: "2026-11-01T00:00:00Z", to: "2026-11-02T00:00:00Z" };
  const original = { ...filters };
  const base = transport();
  const fetchImpl: typeof fetch = async (input, options) => {
    if (String(input).endsWith("/.well-known/agent-card.json")) filters.source = "changed";
    else {
      const data = JSON.parse(String(options?.body)).params.message.parts[0].data;
      expect(data.filters).toEqual(original);
      expect(data.question).toBe("Independent fixture question");
      expect(data).not.toHaveProperty("query");
    }
    return base(input, options);
  };
  const adapter = new A2aResearch(config, auth, fetchImpl);
  for await (const event of adapter.ask("Independent fixture question", new AbortController().signal, undefined, filters)) void event;
  const token = vi.fn(auth.token);
  await expect(async () => {
    for await (const event of new A2aResearch(config, { ...auth, token }, fetchImpl)
      .ask("Fixture", new AbortController().signal, undefined, { from: "invalid" })) void event;
  }).rejects.toThrow("invalid_filters");
  expect(token).not.toHaveBeenCalled();
});
