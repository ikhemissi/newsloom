import { expect, test } from "vitest";
import { parseAnswer } from "../src/answer";
import { clearThread, historyFor, loadThread, MAX_HISTORY_BYTES, saveThread } from "../src/conversation";
import type { Turn } from "../src/conversation";

const id = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`;
function turn(n: number, text = `Answer ${n}.`): Turn {
  return { id: `t${n}`, question: `Question ${n}?`, text, answer: parseAnswer(text), followUps: [`Next ${n}?`], citedItemIds: [id(n)] };
}

test("history sends the last three turns with their cited items", () => {
  const history = historyFor([turn(1), turn(2), turn(3), turn(4)]);
  expect(history.map((entry) => entry.question)).toEqual(["Question 2?", "Question 3?", "Question 4?"]);
  expect(history[0]).toEqual({ question: "Question 2?", answer: "Answer 2.", cited_item_ids: [id(2)] });
});

test("the oldest answer text is trimmed first to stay within 12 KiB", () => {
  const big = "é".repeat(4000);
  const history = historyFor([turn(1, big), turn(2, big), turn(3, "Short answer.")]);
  const size = history.reduce((total, entry) => total + new TextEncoder().encode(entry.question + entry.answer).length, 0);
  expect(size).toBeLessThanOrEqual(MAX_HISTORY_BYTES);
  expect(history.at(-1)?.answer).toBe("Short answer.");
  expect(history.length).toBeGreaterThanOrEqual(2);
  expect(history[0]!.answer.length).toBeLessThan(history[1]!.answer.length);
});

test("the thread round-trips through tab storage, rejects tampering and clears", () => {
  saveThread([turn(1), turn(2)]);
  expect(loadThread().map((entry) => entry.question)).toEqual(["Question 1?", "Question 2?"]);
  expect(loadThread()[0]?.answer.paragraphs[0]?.text).toBe("Answer 1.");
  sessionStorage.setItem("newsloom.conversation", JSON.stringify([{ ...turn(1), extra: true }]));
  expect(loadThread()).toEqual([]);
  sessionStorage.setItem("newsloom.conversation", "{not json");
  expect(loadThread()).toEqual([]);
  saveThread([turn(1)]);
  clearThread();
  expect(sessionStorage.getItem("newsloom.conversation")).toBeNull();
});
