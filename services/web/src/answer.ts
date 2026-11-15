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
    const match = line ? /^\[(W?)([1-9]\d*)\] (.+)$/.exec(line) : null;
    if (!match) break;
    blocks.pop();
    const number = Number(match[2]);
    const url = match[3];
    if (!url || !Number.isSafeInteger(number)) throw new UiFailure("invalid_response");
    const parsed = safeHttps(url);
    citations.unshift({ number, url, href: parsed?.href ?? null, host: parsed?.hostname ?? null,
      ...(match[1] ? { web: true as const } : {}) });
  }
  const stored = citations.filter((citation) => !citation.web);
  const web = citations.filter((citation) => citation.web);
  // Stored citation lines come first, then web lines, each numbered from 1.
  if (stored.some((citation, index) => citation.number !== index + 1)
      || web.some((citation, index) => citation.number !== index + 1)
      || citations.some((citation, index) => !citation.web && citations.slice(0, index).some((other) => other.web)))
    throw new UiFailure("invalid_response");
  const paragraphs = blocks.map((block) => {
    const suffix = /(?: \[W?[1-9]\d*\])+$/.exec(block);
    if (!suffix) return { text: block, references: [] };
    const markers = [...suffix[0].matchAll(/\[(W?)([1-9]\d*)\]/g)];
    const references = markers.filter((match) => !match[1]).map((match) => Number(match[2]));
    const webReferences = markers.filter((match) => match[1]).map((match) => Number(match[2]));
    if (references.some((number) => !stored.some((citation) => citation.number === number))
        || webReferences.some((number) => !web.some((citation) => citation.number === number)))
      throw new UiFailure("invalid_response");
    return { text: block.slice(0, -suffix[0].length), references, ...(webReferences.length ? { webReferences } : {}) };
  });
  return { paragraphs, citations };
}
