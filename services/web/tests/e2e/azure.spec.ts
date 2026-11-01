import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { z } from "zod";
import { writeFile } from "node:fs/promises";

const taskSchema = z.object({
  id: z.string().min(1),
  status: z.object({ state: z.literal("TASK_STATE_COMPLETED"), message: z.object({
    parts: z.array(z.object({ text: z.string() })).length(1),
  }) }),
  artifacts: z.array(z.object({ parts: z.array(z.object({ text: z.string() })).length(1) })).length(1),
});
const receiptSchema = z.object({
  outcome: z.enum(["supported", "limited", "no_match"]),
  user_preserved: z.literal(true), validated: z.literal(true),
  items: z.number().int().min(0).max(10),
  tool_calls: z.number().int().min(1).max(8),
  generation_calls: z.number().int().min(0).max(4),
  usage_observed_calls: z.number().int().min(0).max(4),
  input_tokens: z.number().int().min(0).max(262144),
  output_tokens: z.number().int().min(0).max(4096),
}).strict();

test("deployed reader completes transient sign-in and live research", async ({ page }) => {
  const origin = process.env.NEWSLOOM_UI_ORIGIN;
  const question = process.env.NEWSLOOM_UI_QUESTION;
  if (!origin || !question || new URL(origin).protocol !== "https:")
    throw new Error("Explicit UI origin and authored acceptance question required");
  await page.goto(origin);
  await page.getByRole("button", { name: "Sign in to research" }).click();
  await page.getByLabel("What would you like to understand?").waitFor({ timeout: 180000 });
  await page.getByLabel("What would you like to understand?").fill(question);
  const requestResponse = page.waitForResponse((response) =>
    response.url().endsWith("/a2a") && response.request().method() === "POST"
    && response.request().postDataJSON()?.method === "SendStreamingMessage");
  await page.getByRole("button", { name: "Ask Newsloom" }).click();
  await page.getByLabel("Research answer").waitFor({ timeout: 125000 });
  const response = await requestResponse;
  const bytes = await response.body();
  if (bytes.length > 1048576) throw new Error("ui_acceptance_stream_limit");
  const events: unknown[] = bytes.toString("utf8").split(/\r?\n/)
    .filter((line) => line.startsWith("data:"))
    .map((line) => JSON.parse(line.slice(5)));
  const final = events.map((value) => z.object({
    result: z.object({ task: taskSchema }),
  }).safeParse(value)).findLast((value) => value.success);
  if (!final?.success) throw new Error("ui_acceptance_terminal_missing");
  const task = final.data.result.task;
  const headers = await response.request().allHeaders();
  if (!headers.authorization) throw new Error("ui_acceptance_authorization_missing");
  const readbackResponse = await page.request.post(response.url(), {
    headers: { Authorization: headers.authorization, "A2A-Version": "1.0" },
    data: { jsonrpc: "2.0", id: "ui-acceptance-readback", method: "GetTask",
      params: { id: task.id, historyLength: 0 } },
    failOnStatusCode: false,
  });
  if (readbackResponse.status() !== 200) throw new Error("ui_acceptance_readback_failed");
  const readback = z.object({ result: taskSchema }).parse(await readbackResponse.json()).result;
  if (readback.artifacts[0]?.parts[0]?.text !== task.artifacts[0]?.parts[0]?.text)
    throw new Error("ui_acceptance_answer_parity_failed");
  const receiptPart = readback.status.message.parts[0];
  if (!receiptPart) throw new Error("ui_acceptance_receipt_missing");
  const receipt = receiptSchema.parse(JSON.parse(receiptPart.text));
  if (receipt.generation_calls !== receipt.usage_observed_calls)
    throw new Error("ui_acceptance_usage_incomplete");
  const citationCount = await page.locator(".citations a").count();
  if (!citationCount) throw new Error("ui_acceptance_citations_missing");
  const citation = page.locator(".citations a").first();
  const href = await citation.getAttribute("href");
  if (!href || new URL(href).protocol !== "https:") throw new Error("ui_acceptance_citation_invalid");
  await citation.focus();
  if (!await citation.evaluate((element) => element === document.activeElement))
    throw new Error("ui_acceptance_keyboard_failed");
  const navigation = page.waitForEvent("popup");
  await page.keyboard.press("Enter");
  const popup = await navigation;
  await popup.waitForURL((url) => url.protocol === "https:", { timeout: 30000 });
  await popup.close();
  const results = await new AxeBuilder({ page }).analyze();
  if (results.violations.length)
    throw new Error(`ui_accessibility:${results.violations.map((item) => item.id).join(",")}`);
  const denied = await page.request.post(response.url(), {
    headers: { Origin: origin, "A2A-Version": "1.0" },
    data: { jsonrpc: "2.0", id: "ui-acceptance-denied", method: "GetTask", params: { id: task.id } },
    failOnStatusCode: false,
  });
  expect(denied.status()).toBe(401);
  const output = process.env.NEWSLOOM_UI_ACCEPTANCE_OUTPUT;
  if (output) await writeFile(output, JSON.stringify({
    completed_task_parity: true, citations: citationCount,
    keyboard_citation_navigation: true, accessibility_violations: results.violations.length,
    authorization_denial: denied.status(), ...receipt,
  }, null, 2) + "\n", { mode: 0o600 });
});
