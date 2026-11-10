import { z } from "zod";
import type { Answer, HistoryTurn } from "./domain";
import { parseAnswer, utf8Size } from "./answer";

export const MAX_HISTORY_TURNS = 3;
export const MAX_HISTORY_BYTES = 12 * 1024;
const KEY = "newsloom.conversation";

export type Turn = {
  id: string; question: string; text: string; answer: Answer;
  followUps: string[]; citedItemIds: string[];
};

const storedSchema = z.array(z.object({
  id: z.string().min(1).max(64), question: z.string().min(1).max(8192), text: z.string().min(1).max(16384),
  followUps: z.array(z.string().max(120)).max(3), citedItemIds: z.array(z.uuid()).max(10),
}).strict()).max(20);

/** The thread lives only in this browser tab and is re-validated when read back. */
export function loadThread(storage: Storage = sessionStorage): Turn[] {
  try {
    const parsed = storedSchema.safeParse(JSON.parse(storage.getItem(KEY) ?? "[]"));
    if (!parsed.success) return [];
    return parsed.data.map((turn) => ({ ...turn, answer: parseAnswer(turn.text) }));
  } catch { return []; }
}

export function saveThread(turns: readonly Turn[], storage: Storage = sessionStorage): void {
  try {
    if (!turns.length) { storage.removeItem(KEY); return; }
    storage.setItem(KEY, JSON.stringify(turns.slice(-20).map((turn) => ({
      id: turn.id, question: turn.question, text: turn.text, followUps: turn.followUps, citedItemIds: turn.citedItemIds,
    }))));
  } catch { /* Storage full or disabled: the thread stays in memory only. */ }
}

export function clearThread(storage: Storage = sessionStorage): void {
  try { storage.removeItem(KEY); } catch { /* Nothing stored. */ }
}

function truncate(value: string, bytes: number): string {
  let result = value;
  while (result && utf8Size(result) > bytes) result = result.slice(0, Math.max(0, result.length - Math.max(1, utf8Size(result) - bytes)));
  return result;
}

/** The last three turns, trimming the oldest answer text first to stay within 12 KiB. */
export function historyFor(turns: readonly Turn[]): HistoryTurn[] {
  const history = turns.slice(-MAX_HISTORY_TURNS).map((turn) => ({
    question: turn.question, answer: turn.text, cited_item_ids: [...turn.citedItemIds],
  }));
  const size = () => history.reduce((total, turn) => total + utf8Size(turn.question) + utf8Size(turn.answer), 0);
  for (const turn of history) {
    const excess = size() - MAX_HISTORY_BYTES;
    if (excess <= 0) break;
    turn.answer = truncate(turn.answer, Math.max(0, utf8Size(turn.answer) - excess));
  }
  while (history.length && size() > MAX_HISTORY_BYTES) history.shift();
  return history.filter((turn) => turn.answer.trim());
}
