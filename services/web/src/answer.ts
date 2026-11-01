import { safeHttps } from "./config";
import type { Answer, Citation } from "./domain";
import { UiFailure } from "./domain";

export const MAX_ANSWER_BYTES = 16384;
export const utf8Size = (value: string) => new TextEncoder().encode(value).length;

export function validateQuestion(value: string): string {
  const question = value.trim();
  if (!question || utf8Size(question) > 8192
      || /[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/.test(question))
    throw new UiFailure("invalid_input");
  return question;
}

export function parseAnswer(text: string): Answer {
  if (!text.trim() || utf8Size(text) > MAX_ANSWER_BYTES) throw new UiFailure("invalid_response");
  const blocks = text.split("\n\n");
  const citations: Citation[] = [];
  while (blocks.length) {
    const line = blocks.at(-1);
    const match = line ? /^\[([1-9]\d*)\] (.+)$/.exec(line) : null;
    if (!match) break;
    blocks.pop();
    const number = Number(match[1]);
    const url = match[2];
    if (!url || !Number.isSafeInteger(number)) throw new UiFailure("invalid_response");
    const parsed = safeHttps(url);
    citations.unshift({ number, url, href: parsed?.href ?? null, host: parsed?.hostname ?? null });
  }
  if (citations.some((citation, index) => citation.number !== index + 1))
    throw new UiFailure("invalid_response");
  const paragraphs = blocks.map((block) => {
    const suffix = /(?: \[[1-9]\d*\])+$/.exec(block);
    if (!suffix) return { text: block, references: [] };
    const references = [...suffix[0].matchAll(/\[([1-9]\d*)\]/g)].map((match) => Number(match[1]));
    if (references.some((number) => !citations.some((citation) => citation.number === number)))
      throw new UiFailure("invalid_response");
    return { text: block.slice(0, -suffix[0].length), references };
  });
  return { paragraphs, citations };
}
