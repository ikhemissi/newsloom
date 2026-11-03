// @vitest-environment node
import { createServer } from "node:http";
import { once } from "node:events";
import { afterAll, beforeAll, expect, test, vi } from "vitest";
import { HttpCatalog } from "../src/catalog";
import { parseBriefing } from "../src/briefing";
import { architectBriefing, briefingResponse, legacyBriefing, noMaterialBriefing, runtimeConfig } from "./fixtures";

const auth = {
  signedIn: () => true, signIn: async () => undefined, signOut: async () => undefined,
  token: vi.fn(async () => "authored-token"),
};
const signal = () => new AbortController().signal;
const client = (fetchImpl: typeof fetch = fetch) => new HttpCatalog(runtimeConfig, auth, fetchImpl);
const server = createServer((request, response) => {
  if (request.url !== "/api/v1/briefing" || request.method !== "GET"
      || request.headers.authorization !== "Bearer authored-token") {
    response.writeHead(400).end(); return;
  }
  response.writeHead(200, { "content-type": "application/json" });
  response.end(JSON.stringify(briefingResponse));
});
let endpoint = "";
beforeAll(async () => {
  server.listen(0, "127.0.0.1"); await once(server, "listening");
  const address = server.address();
  if (!address || typeof address === "string") throw new Error("fixture_startup");
  endpoint = `http://127.0.0.1:${address.port}/api/v1`;
});
afterAll(async () => { server.close(); await once(server, "close"); });

test("actual HttpCatalog performs only the authorized GET and retains exact offset strings", async () => {
  const paths: string[] = [];
  const catalog = new HttpCatalog({ ...runtimeConfig, newsApiUrl: endpoint }, auth, async (input, options) => {
    paths.push(new URL(String(input)).pathname);
    expect(options?.cache).toBe("no-store");
    expect(options?.credentials).toBe("omit");
    expect(options?.redirect).toBe("error");
    return fetch(input, options);
  });
  expect(await catalog.briefing(signal())).toEqual(briefingResponse);
  expect(paths).toEqual(["/api/v1/briefing"]);
  expect(auth.token).toHaveBeenCalledWith("news");
});

test("strict briefing DTO rejects invalid shape, dates, counts, coverage, windows, citations and freshness", () => {
  const change = (mutate: (value: typeof briefingResponse) => void) => {
    const value = structuredClone(briefingResponse); mutate(value); return value;
  };
  const artifactChange = (mutate: (value: NonNullable<typeof briefingResponse.briefing>) => void) =>
    change((value) => { if (value.briefing) mutate(value.briefing); });
  for (const body of [
    {}, { ...briefingResponse, extra: true },
    change((value) => { value.meta.result_scope = "page" as "briefing"; }),
    change((value) => { value.meta.cache_age_seconds = Infinity; }),
    change((value) => { value.meta.cache_age_seconds = -1; }),
    change((value) => { value.meta.read_at = "2026-11-02T05:00:00"; }),
    change((value) => { value.refresh.stale = true; }),
    change((value) => { value.refresh.expected_cutoff = "2026-11-01T05:00:00Z"; }),
    change((value) => { value.briefing = null; }),
    artifactChange((value) => { value.version = "not-a-uuid"; }),
    artifactChange((value) => { value.generated_at = "2026-11-02T04:59:59Z"; }),
    artifactChange((value) => { value.window_start = "2026-10-25T05:00:00Z"; }),
    artifactChange((value) => { value.window_end = "2026-11-02T06:00:00Z"; value.window_start = "2026-10-26T06:00:00Z"; }),
    artifactChange((value) => { value.coverage = "other" as "full"; }),
    artifactChange((value) => { value.evidence_count = -1; }),
    artifactChange((value) => { value.evidence_count = 1.5; }),
    artifactChange((value) => { value.evidence_count = 0; }),
    artifactChange((value) => { value.tldr = null; }),
    artifactChange((value) => { value.tldr = { text: "Two\nparagraphs", references: [1] }; }),
    artifactChange((value) => { value.sections = []; }),
    artifactChange((value) => { value.sections[0]!.paragraphs[0]!.text = "Short."; }),
    artifactChange((value) => { value.sections[0]!.paragraphs[0]!.text = "word ".repeat(1101); }),
    artifactChange((value) => { value.tldr!.references = [2]; }),
    artifactChange((value) => { value.sections[0]!.paragraphs[0]!.references = [0]; }),
    artifactChange((value) => { value.citations[0]!.number = 2; }),
    artifactChange((value) => { value.citations.push(value.citations[0]!); }),
    ...["javascript:alert(1)", "http://publisher.test", "https://user:pass@publisher.test", "/relative"].map((url) =>
      artifactChange((value) => { value.citations[0]!.url = url; })),
    artifactChange((value) => { value.coverage = "empty"; }),
  ]) expect(() => parseBriefing(body)).toThrow("invalid_response");
});

test("900/1100 full narrative boundaries exclude TLDR/headings; limited and empty are distinct", () => {
  for (const count of [899, 900, 1100, 1101]) {
    const body = structuredClone(briefingResponse);
    body.briefing!.sections = [{
      heading: "heading ".repeat(1200), paragraphs: [{ text: "word ".repeat(count).trim(), references: [1] }],
    }];
    body.briefing!.tldr!.text = "word ".repeat(100);
    if (count === 900 || count === 1100) expect(parseBriefing(body)).toEqual(body);
    else expect(() => parseBriefing(body)).toThrow("invalid_response");
  }
  const limited = structuredClone(briefingResponse);
  limited.briefing!.coverage = "limited";
  limited.briefing!.sections = [{ heading: "Limited evidence", paragraphs: [{ text: "A short supported overview.", references: [1] }] }];
  expect(parseBriefing(limited)).toEqual(limited);
  const empty = structuredClone(briefingResponse);
  empty.briefing = { ...empty.briefing!, coverage: "empty", evidence_count: 0, tldr: null, sections: [], citations: [] };
  expect(parseBriefing(empty)).toEqual(empty);
  const pending = { ...empty, briefing: null, refresh: { ...empty.refresh, state: "pending" as const, stale: true } };
  expect(parseBriefing(pending)).toEqual(pending);
  expect(() => parseBriefing({ ...empty, briefing: { ...empty.briefing, citations: briefingResponse.briefing!.citations } }))
    .toThrow("invalid_response");
  const offset = structuredClone(briefingResponse);
  offset.briefing!.window_start = "2026-10-26T06:00:00+01:00";
  offset.briefing!.window_end = "2026-11-02T06:00:00+01:00";
  expect(parseBriefing(offset).briefing?.window_end).toBe("2026-11-02T06:00:00+01:00");
});

test("briefing lane is independent, permits cancellation and rejects concurrent same-lane reads", async () => {
  const blocked = new AbortController();
  const fetchImpl = vi.fn<typeof fetch>(async (_input, options) => {
    await new Promise<void>((_, reject) => {
      options?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true });
    });

    test("architect policy accepts short full paragraphs and exactly 1000 combined words, not 1001", () => {
      const short = architectBriefing();
      short.briefing!.sections[0]!.paragraphs = [
        { text: "The SDK changes its authentication interface.", references: [1] },
        { text: "Architects should review migration requirements before upgrading.", references: [] },
      ];
      expect(parseBriefing(short)).toEqual(short);
      for (const coverage of ["full", "limited"] as const) {
        const exact = architectBriefing(920, 80);
        exact.briefing!.coverage = coverage;
        exact.briefing!.sections[0]!.heading = "heading ".repeat(1200);
        expect(parseBriefing(exact)).toEqual(exact);
        exact.briefing!.tldr!.text += " extra";
        expect(() => parseBriefing(exact)).toThrow("invalid_response");
      }
      for (const editorial_policy of [undefined, null] as const) {
        const legacy = legacyBriefing();
        if (editorial_policy === null) legacy.briefing!.editorial_policy = null;
        expect(parseBriefing(legacy)).toEqual(legacy);
        const shortLegacy = architectBriefing();
        if (editorial_policy === null) shortLegacy.briefing!.editorial_policy = null;
        else delete shortLegacy.briefing!.editorial_policy;
        expect(() => parseBriefing(shortLegacy)).toThrow("invalid_response");
      }
      const unknown = architectBriefing();
      expect(() => parseBriefing({ ...unknown, briefing: { ...unknown.briefing, editorial_policy: "architect-v2" } }))
        .toThrow("invalid_response");
    });

    test("no-material result requires architect policy, reviewed evidence and no generated content", () => {
      const result = noMaterialBriefing();
      expect(parseBriefing(result)).toEqual(result);
      for (const patch of [
        { editorial_policy: undefined }, { editorial_policy: null }, { evidence_count: 0 },
        { tldr: briefingResponse.briefing!.tldr }, { sections: briefingResponse.briefing!.sections },
        { citations: briefingResponse.briefing!.citations },
      ]) expect(() => parseBriefing({ ...result, briefing: { ...result.briefing, ...patch } }))
        .toThrow("invalid_response");
    });
    return Response.json({});
  });
  const catalog = client(fetchImpl);
  const pending = catalog.briefing(blocked.signal);
  const failed = expect(pending).rejects.toThrow("timeout");
  await vi.waitFor(() => expect(fetchImpl).toHaveBeenCalledOnce());
  await expect(catalog.briefing(signal())).rejects.toThrow("overloaded");
  const news = catalog.recent(blocked.signal);
  const newsFailed = expect(news).rejects.toThrow("timeout");
  await vi.waitFor(() => expect(fetchImpl).toHaveBeenCalledTimes(2));
  blocked.abort();
  await Promise.all([failed, newsFailed]);
});

test("read failures and the existing 1 MiB transport bound cannot become no-news results", async () => {
  for (const status of [401, 403, 404, 429, 500, 503]) {
    const fetchImpl = vi.fn(async () => Response.json({ error: "PRIVATE_CANARY" }, { status }));
    await expect(client(fetchImpl).briefing(signal())).rejects.toThrow();
    expect(fetchImpl).toHaveBeenCalledOnce();
  }
  await expect(client(async () => new Response(" ".repeat(1024 * 1024 + 1),
    { headers: { "content-type": "application/json" } })).briefing(signal())).rejects.toThrow("invalid_response");
  await expect(client(async () => Response.json({ briefing: null })).briefing(signal())).rejects.toThrow("invalid_response");
});
