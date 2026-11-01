import { z } from "zod";
import { UiFailure } from "./domain";

export function safeHttps(value: string): URL | null {
  try {
    const url = new URL(value);
    return url.protocol === "https:" && !url.username && !url.password ? url : null;
  } catch { return null; }
}

const interfaceUrl = (path: string) => z.string().refine((value) => {
  const url = safeHttps(value);
  return url !== null && url.pathname === path && !url.search && !url.hash
    && (!url.port || url.port === "443");
});
const scope = (name: string) => z.string().refine((value) => {
  const prefix = "api://";
  const suffix = `/${name}`;
  return value.startsWith(prefix) && value.endsWith(suffix)
    && z.uuid().safeParse(value.slice(prefix.length, -suffix.length)).success;
});

const configSchema = z.object({
  tenantId: z.uuid(), clientId: z.uuid(),
  agentUrl: interfaceUrl("/a2a"), agentScope: scope("news.agent"),
  mcpUrl: interfaceUrl("/mcp"), mcpScope: scope("news.read"),
}).strict().refine((value) =>
  value.agentScope !== `api://${value.clientId}/news.agent`
  && value.mcpScope !== `api://${value.clientId}/news.read`
  && value.agentScope.split("/news.")[0] !== value.mcpScope.split("/news.")[0]);

export type RuntimeConfig = z.infer<typeof configSchema>;

export function parseConfig(value: unknown): RuntimeConfig {
  const result = configSchema.safeParse(value);
  if (!result.success) throw new UiFailure("configuration");
  return result.data;
}

export async function loadConfig(fetchImpl: typeof fetch = fetch): Promise<RuntimeConfig> {
  try {
    const response = await fetchImpl("/config.json", {
      cache: "no-store", credentials: "omit", redirect: "error", signal: AbortSignal.timeout(10000),
    });
    if (!response.ok) throw new UiFailure("configuration");
    const reader = response.body?.getReader();
    if (!reader) throw new UiFailure("configuration");
    const chunks: Uint8Array[] = [];
    let size = 0;
    try {
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        size += value.length;
        if (size > 8192) throw new UiFailure("configuration");
        chunks.push(value);
      }
    } finally { await reader.cancel(); }
    const bytes = new Uint8Array(size);
    let offset = 0;
    for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
    return parseConfig(JSON.parse(new TextDecoder().decode(bytes)));
  } catch { throw new UiFailure("configuration"); }
}
