import { expect, test } from "vitest";
import { parseAnswer, validateQuestion } from "../src/answer";
import { parseConfig, safeHttps } from "../src/config";
import { runtimeConfig } from "./fixtures";

test("question bounds are UTF-8 bytes, not UTF-16 characters", () => {
  expect(validateQuestion("a".repeat(8192)).length).toBe(8192);
  expect(validateQuestion("\u00e9".repeat(4096)).length).toBe(4096);
  for (const value of [" ", "a".repeat(8193), "\u00e9".repeat(4097), "a\uD800b", "a\uDC00b"])
    expect(() => validateQuestion(value)).toThrow("invalid_input");
  expect(validateQuestion("a\u0000b")).toBe("a\u0000b");
});

test("citations map the actual trailing footer without losing unknown text", () => {
  const answer = parseAnswer("Claim [1]\n\nLimitation: limited evidence.\n\nUnrecognized paragraph.\n\n[1] https://publisher.test/article");
  expect(answer.paragraphs.map((value) => value.text)).toEqual([
    "Claim", "Limitation: limited evidence.", "Unrecognized paragraph.",
  ]);
  expect(answer.paragraphs[0]?.references).toEqual([1]);
  expect(answer.citations[0]?.host).toBe("publisher.test");
});

test("unsafe links remain inert and malformed citation structures fail", () => {
  for (const url of ["javascript:alert(1)", "data:text/html,bad", "https://user:password@publisher.test/"])
    expect(parseAnswer(`Claim [1]\n\n[1] ${url}`).citations[0]?.href).toBeNull();
  for (const value of ["Claim [2]\n\n[1] https://publisher.test", "Claim [1]\n\n[2] https://publisher.test",
    "Claim [1]\n\n[1] https://publisher.test\n\n[1] https://publisher.test", "a".repeat(16385)])
    expect(() => parseAnswer(value)).toThrow("invalid_response");
  expect(parseAnswer("<script>bad()</script>").paragraphs[0]?.text).toBe("<script>bad()</script>");
  expect(parseAnswer("a".repeat(16384)).paragraphs[0]?.text.length).toBe(16384);
});

test("configuration and HTTPS links do not accept caller-selected or unsafe values", () => {
  const config = runtimeConfig;
  expect(parseConfig(config)).toEqual(config);
  for (const value of [{}, { ...config, agentUrl: "http://agent.test/a2a" },
    { ...config, agentUrl: "https://user@agent.test/a2a" }, { ...config, extra: true },
    { ...config, newsApiUrl: "https://mcp.test/mcp" },
    { ...config, newsApiUrl: "https://mcp.test/api/v1?redirect=untrusted" },
    { ...config, mcpUrl: "https://mcp.test/mcp" },
    { ...config, newsScope: config.agentScope.replace("news.agent", "news.read") },
    { ...config, agentScope: `api://${config.clientId}/news.agent` }])
    expect(() => parseConfig(value)).toThrow("configuration");
  expect(safeHttps("javascript:alert(1)")).toBeNull();
});
