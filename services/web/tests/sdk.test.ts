import { AgentCard, SendMessageRequest, TaskState } from "@a2a-js/sdk";
import { ClientFactory, DefaultAgentCardResolver, JsonRpcTransportFactory } from "@a2a-js/sdk/client";
import { expect, test } from "vitest";
import { z } from "zod";

const endpoint = "https://agent.test/a2a";
const task = {
  id: "fixture-task",
  contextId: "fixture-context",
  status: { state: "TASK_STATE_COMPLETED" },
  artifacts: [{ artifactId: "answer", parts: [{ text: "Fixture answer." }] }],
};

test("official SDK uses the deployed 1.0 JSON-RPC wire contract and cancellation signal", async () => {
  const methods: string[] = [];
  const controller = new AbortController();
  const fetchImpl: typeof fetch = async (input, options) => {
    expect(String(input)).toBe(endpoint);
    expect(options?.signal).toBe(controller.signal);
    const headers = new Headers(options?.headers);
    expect(headers.get("A2A-Version")).toBe("1.0");
    expect(headers.has("A2A-Extensions")).toBe(false);
    expect(headers.get("Content-Type")).toBe("application/json");
    const request = z.object({
      jsonrpc: z.literal("2.0"), id: z.number(), method: z.string(),
      params: z.record(z.string(), z.unknown()),
    }).strict().parse(JSON.parse(String(options?.body)));
    methods.push(request.method);
    if (request.method === "SendStreamingMessage") {
      expect(request.params).toEqual({
        message: {
          messageId: "fixture-message", role: "ROLE_USER",
          parts: [{ data: { operation: "research", question: "Fixture question" }, mediaType: "application/json" }],
        },
        configuration: { acceptedOutputModes: ["text/plain"] },
      });
      return new Response(`data: ${JSON.stringify({ jsonrpc: "2.0", id: request.id, result: { task } })}\n\n`, {
        headers: { "Content-Type": "text/event-stream" },
      });
    }
    expect(["GetTask", "CancelTask"]).toContain(request.method);
    return Response.json({ jsonrpc: "2.0", id: request.id, result: {
      ...task, status: { state: request.method === "CancelTask" ? "TASK_STATE_CANCELED" : "TASK_STATE_COMPLETED" },
    } });
  };
  const card = AgentCard.fromJSON({
    name: "Fixture", version: "1", capabilities: { streaming: true },
    supportedInterfaces: [{ url: endpoint, protocolBinding: "JSONRPC", protocolVersion: "1.0" }],
    defaultInputModes: ["application/json"], defaultOutputModes: ["text/plain"],
  });
  const client = await new ClientFactory({
    transports: [new JsonRpcTransportFactory({ fetchImpl })],
    preferredTransports: ["JSONRPC"],
  }).createFromAgentCard(card);
  const events = [];
  for await (const event of client.sendMessageStream(SendMessageRequest.fromJSON({
    message: {
      messageId: "fixture-message", role: "ROLE_USER",
      parts: [{ data: { operation: "research", question: "Fixture question" }, mediaType: "application/json" }],
    },
    configuration: { acceptedOutputModes: ["text/plain"] },
  }), { signal: controller.signal })) events.push(event);
  expect(events[0]?.payload?.$case).toBe("task");
  const readback = await client.getTask({ id: "fixture-task", tenant: "" }, { signal: controller.signal });
  expect(readback.status?.state).toBe(TaskState.TASK_STATE_COMPLETED);
  const stopped = await client.cancelTask({ id: "fixture-task", tenant: "", metadata: undefined }, { signal: controller.signal });
  expect(stopped.status?.state).toBe(TaskState.TASK_STATE_CANCELED);
  expect(methods).toEqual(["SendStreamingMessage", "GetTask", "CancelTask"]);
});

test("discovery is public and selects only JSON-RPC 1.0", async () => {
  const cardResolver = new DefaultAgentCardResolver({ fetchImpl: async (input, options) => {
    expect(String(input)).toBe("https://agent.test/.well-known/agent-card.json");
    expect(new Headers(options?.headers).has("Authorization")).toBe(false);
    return Response.json({
      name: "Fixture", version: "1", capabilities: { streaming: true },
      supportedInterfaces: [{ url: endpoint, protocolBinding: "JSONRPC", protocolVersion: "1.0" }],
      defaultInputModes: ["application/json"], defaultOutputModes: ["text/plain"],
    });
  } });
  const client = await new ClientFactory({
    transports: [new JsonRpcTransportFactory()], preferredTransports: ["JSONRPC"], cardResolver,
  }).createFromUrl("https://agent.test");
  expect(client.protocolVersion).toBe("1.0");
});

test("abort propagates to an actual pending SDK fetch", async () => {
  const controller = new AbortController();
  const card = AgentCard.fromJSON({
    supportedInterfaces: [{ url: endpoint, protocolBinding: "JSONRPC", protocolVersion: "1.0" }],
  });
  const client = await new ClientFactory({
    transports: [new JsonRpcTransportFactory({ fetchImpl: async (_, options) =>
      new Promise<Response>((_, reject) => {
        options?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true });
        queueMicrotask(() => controller.abort());
      }) })],
  }).createFromAgentCard(card);
  await expect(client.getTask({ id: "fixture-task", tenant: "" }, { signal: controller.signal }))
    .rejects.toMatchObject({ name: "AbortError" });
});
