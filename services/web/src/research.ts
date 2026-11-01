import { SendMessageRequest, TaskState } from "@a2a-js/sdk";
import type { AgentCard } from "@a2a-js/sdk";
import { ClientFactory, DefaultAgentCardResolver, JsonRpcTransportFactory } from "@a2a-js/sdk/client";
import type { Client } from "@a2a-js/sdk/client";
import { z } from "zod";
import type { RuntimeConfig } from "./config";
import type { AuthSession, ResearchClient, ResearchEvent } from "./domain";
import { accessToken, UiFailure } from "./domain";
import { MAX_ANSWER_BYTES, parseAnswer, utf8Size, validateQuestion } from "./answer";

const progressSchema = z.object({
  phase: z.enum(["retrieving", "planning", "synthesizing", "validating"]),
  tool_calls: z.number().int().min(0).max(8), evidence_items: z.number().int().min(0).max(10),
}).strict();

type ActiveRequest = {
  controller: AbortController; client: Client | null; card: AgentCard | null;
  taskId: string | null; token: string | null;
};

function validateCard(card: AgentCard, config: RuntimeConfig): void {
  const endpoint = card.supportedInterfaces[0];
  const scheme = card.securitySchemes.entra?.scheme;
  const flow = scheme?.$case === "oauth2SecurityScheme" ? scheme.value.flows?.flow : null;
  if (card.supportedInterfaces.length !== 1 || endpoint?.url !== config.agentUrl
      || endpoint.protocolBinding !== "JSONRPC" || endpoint.protocolVersion !== "1.0"
      || !card.capabilities?.streaming || card.capabilities.pushNotifications
      || card.defaultOutputModes.length !== 1 || card.defaultOutputModes[0] !== "text/plain"
      || !card.defaultInputModes.includes("application/json")
      || !card.skills.some((skill) => skill.id === "research")
      || Object.keys(card.securitySchemes).length !== 1
      || flow?.$case !== "authorizationCode" || !flow.value.pkceRequired
      || Object.keys(flow.value.scopes).length !== 1 || !(config.agentScope in flow.value.scopes)
      || card.securityRequirements.length !== 1
      || Object.keys(card.securityRequirements[0]?.schemes ?? {}).length !== 1
      || card.securityRequirements[0]?.schemes.entra?.list.length !== 1
      || card.securityRequirements[0]?.schemes.entra?.list[0] !== config.agentScope)
    throw new UiFailure("invalid_response");
}

export function guardedFetch(
  endpoint: string, token: string | null, signal: AbortSignal, fetchImpl: typeof fetch = fetch,
): typeof fetch {
  let total = 0;
  return async (input, options) => {
    if (String(input) !== endpoint) throw new UiFailure("invalid_response");
    const headers = new Headers(options?.headers);
    if (token) headers.set("Authorization", `Bearer ${token}`);
    else if (headers.has("Authorization")) throw new UiFailure("invalid_response");
    if (headers.has("A2A-Extensions")) throw new UiFailure("invalid_response");
    let response: Response;
    try {
      response = await fetchImpl(input, { ...options, headers, signal, credentials: "omit", redirect: "error" });
    } catch { throw new UiFailure(signal.aborted ? "timeout" : "unavailable"); }
    if (!response.ok) {
      await response.body?.cancel();
      throw new UiFailure(response.status === 401 || response.status === 403 ? "authorization"
        : response.status === 429 ? "overloaded" : response.status === 504 ? "timeout" : "unavailable");
    }
    if (!response.body) throw new UiFailure("invalid_response");
    const reader = response.body.getReader();
    const body = new ReadableStream<Uint8Array>({
      async pull(controller) {
        try {
          const { value, done } = await reader.read();
          if (done) { controller.close(); return; }
          total += value.length;
          if (total > 1048576) {
            await reader.cancel();
            controller.error(new UiFailure("invalid_response"));
            return;
          }
          controller.enqueue(value);
        } catch { controller.error(new UiFailure(signal.aborted ? "timeout" : "unavailable")); }
      },
      async cancel() { await reader.cancel(); },
    });
    return new Response(body, { status: response.status, headers: response.headers });
  };
}

export class A2aResearch implements ResearchClient {
  private active: ActiveRequest | null = null;
  constructor(private config: RuntimeConfig, private auth: AuthSession, private fetchImpl: typeof fetch = fetch) {}

  async *ask(value: string, signal: AbortSignal, itemIds?: readonly string[]): AsyncIterable<ResearchEvent> {
    if (this.active) throw new UiFailure("overloaded");
    const question = validateQuestion(value);
    if (itemIds && (!itemIds.length || itemIds.length > 5
        || new Set(itemIds.map((id) => id.toLowerCase())).size !== itemIds.length
        || itemIds.some((id) => !z.uuid().safeParse(id).success)))
      throw new UiFailure("invalid_input");
    const state: ActiveRequest = { controller: new AbortController(), client: null, card: null, taskId: null, token: null };
    this.active = state;
    const abort = () => state.controller.abort();
    signal.addEventListener("abort", abort, { once: true });
    if (signal.aborted) abort();
    const timer = setTimeout(abort, 120000);
    try {
      const origin = new URL(this.config.agentUrl).origin;
      const card = await new DefaultAgentCardResolver({
        fetchImpl: guardedFetch(`${origin}/.well-known/agent-card.json`, null, state.controller.signal, this.fetchImpl),
      }).resolve(origin);
      validateCard(card, this.config);
      state.card = card;
      state.token = await accessToken(this.auth, "agent", state.controller.signal);
      state.client = await new ClientFactory({
        transports: [new JsonRpcTransportFactory({
          fetchImpl: guardedFetch(this.config.agentUrl, state.token, state.controller.signal, this.fetchImpl),
        })], preferredTransports: ["JSONRPC"],
      }).createFromAgentCard(card);
      let text = "";
      let artifactId: string | null = null;
      let completed = false;
      let contextId: string | null = null;
      for await (const event of state.client.sendMessageStream(SendMessageRequest.fromJSON({
        message: { messageId: crypto.randomUUID(), role: "ROLE_USER",
          parts: [{ data: { operation: "research", question, ...(itemIds ? { item_ids: [...itemIds] } : {}) },
            mediaType: "application/json" }] },
        configuration: { acceptedOutputModes: ["text/plain"] },
      }), { signal: state.controller.signal })) {
        const payload = event.payload;
        if (!payload || payload.$case === "message" || completed) throw new UiFailure("invalid_response");
        const update = payload.value;
        const id = payload.$case === "task" ? payload.value.id : payload.value.taskId;
        if (!id || (state.taskId && state.taskId !== id)
            || (contextId && contextId !== update.contextId)) throw new UiFailure("invalid_response");
        state.taskId = id;
        contextId = update.contextId;
        if (payload.$case === "artifactUpdate") {
          const artifact = payload.value.artifact;
          const content = artifact?.parts[0]?.content;
          if (!artifact || !artifact.artifactId || artifact.parts.length !== 1 || content?.$case !== "text"
              || !["", "text/plain"].includes(artifact.parts[0]?.mediaType ?? "")
              || (artifactId && (artifactId !== artifact.artifactId || !payload.value.append))
              || (!artifactId && payload.value.append)) throw new UiFailure("invalid_response");
          artifactId = artifact.artifactId;
          text += content.value;
          if (utf8Size(text) > MAX_ANSWER_BYTES) throw new UiFailure("invalid_response");
          continue;
        }
        const status = payload.value.status;
        if (!status) throw new UiFailure("invalid_response");
        if (status.state === TaskState.TASK_STATE_COMPLETED) {
          if (payload.$case === "statusUpdate") continue;
          if (payload.$case !== "task" || payload.value.artifacts.length !== 1
              || payload.value.artifacts[0]?.artifactId !== artifactId
              || payload.value.artifacts[0]?.parts.length !== 1
              || payload.value.artifacts[0]?.parts[0]?.content?.$case !== "text"
              || payload.value.artifacts[0]?.parts[0]?.content?.value !== text)
            throw new UiFailure("invalid_response");
          completed = true;
        } else if (status.state === TaskState.TASK_STATE_FAILED || status.state === TaskState.TASK_STATE_REJECTED
          || status.state === TaskState.TASK_STATE_AUTH_REQUIRED || status.state === TaskState.TASK_STATE_CANCELED) {
          const part = status.message?.parts.length === 1 ? status.message.parts[0]?.content : null;
          const category = part?.$case === "text" ? part.value : "";
          throw new UiFailure(status.state === TaskState.TASK_STATE_CANCELED ? "cancelled"
            : status.state === TaskState.TASK_STATE_AUTH_REQUIRED || category === "authorization_expired"
              ? "authorization" : category === "request_timeout" ? "timeout" : "unavailable");
        } else if (payload.$case === "statusUpdate" && status.message) {
          const part = status.message.parts[0]?.content;
          if (status.message.parts.length !== 1 || part?.$case !== "text")
            throw new UiFailure("invalid_response");
          const result = progressSchema.safeParse(JSON.parse(part.value));
          if (!result.success) throw new UiFailure("invalid_response");
          yield { kind: "progress", phase: result.data.phase };
        }
      }
      if (!completed || signal.aborted || state.controller.signal.aborted) throw new UiFailure("invalid_response");
      yield { kind: "answer", answer: parseAnswer(text) };
    } catch (error) {
      if (error instanceof UiFailure) throw error;
      throw new UiFailure(state.controller.signal.aborted ? "timeout" : "invalid_response");
    } finally {
      clearTimeout(timer);
      signal.removeEventListener("abort", abort);
      state.controller.abort();
      this.active = null;
    }
  }

  async stop(): Promise<boolean> {
    const state = this.active;
    if (!state) return true;
    state.controller.abort();
    if (!state.card || !state.taskId || !state.token) return false;
    try {
      const signal = AbortSignal.timeout(5000);
      const client = await new ClientFactory({
        transports: [new JsonRpcTransportFactory({
          fetchImpl: guardedFetch(this.config.agentUrl, state.token, signal, this.fetchImpl),
        })], preferredTransports: ["JSONRPC"],
      }).createFromAgentCard(state.card);
      const task = await client.cancelTask({ id: state.taskId, tenant: "", metadata: undefined }, {
        signal,
      });
      return task.status?.state === TaskState.TASK_STATE_CANCELED;
    } catch { return false; }
  }
}
