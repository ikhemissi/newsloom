import { useEffect, useState } from "react";
import type { FeedbackClient, FeedbackTarget, Rating, ResearchSnapshot, ReviewItem, ReviewQuery } from "./feedback";
import { MAX_COMMENT, validateComment } from "./feedback";
import { UiFailure, failureMessage } from "./domain";

const labels: Record<Rating, string> = { up: "Helpful", down: "Not helpful" };

/** Thumbs up/down with an optional comment; never triggers generation or research. */
export function FeedbackControls({ client, target, snapshot, label }: {
  client: FeedbackClient; target: FeedbackTarget; snapshot?: ResearchSnapshot; label: string;
}) {
  const [current, setCurrent] = useState<Rating | null>(null);
  const [choice, setChoice] = useState<Rating | null>(null);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    setCurrent(null); setChoice(null); setComment(""); setStatus("");
    client.mine(target, controller.signal).then((vote) => {
      if (!controller.signal.aborted && vote) setCurrent(vote.rating);
    }).catch(() => undefined);
    return () => controller.abort();
  }, [client, target.type, target.ref]);
  const length = [...comment].length;
  async function send() {
    if (!choice || busy) return;
    setBusy(true); setStatus("");
    try {
      await client.submit({ target, rating: choice, comment: validateComment(comment),
        ...(snapshot ? { snapshot } : {}) }, new AbortController().signal);
      setCurrent(choice); setChoice(null); setComment("");
      setStatus("Thanks, your feedback was recorded.");
    } catch (failure) {
      setStatus(failure instanceof UiFailure && failure.category === "invalid_input"
        ? "Feedback could not be accepted. Keep comments to 1,000 characters."
        : `Feedback was not recorded. ${failureMessage(failure)}`);
    } finally { setBusy(false); }
  }
  return <section aria-label={label} className="feedback">
    <div className="feedback-buttons" role="group" aria-label={label}>
      {(["up", "down"] as const).map((rating) => <button key={rating} type="button"
        className={`btn btn-xs ${(choice ?? current) === rating ? "btn-active" : "btn-outline"}`}
        aria-pressed={(choice ?? current) === rating} disabled={busy}
        onClick={() => { setChoice(rating); setStatus(""); }}>
        <span aria-hidden="true">{rating === "up" ? "👍" : "👎"}</span> {labels[rating]}
      </button>)}
      {current && !choice && <span className="feedback-current">Your rating: {labels[current]}</span>}
    </div>
    {choice && <div className="feedback-form">
      <label className="feedback-comment">
        <span>Comment (optional)</span>
        <textarea className="textarea textarea-sm" value={comment} maxLength={MAX_COMMENT}
          onChange={(event) => setComment(event.target.value)}
          onKeyDown={(event) => {
            // Enter sends; Shift+Enter adds a line; IME composition is left alone.
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault(); void send();
            }
          }}
          placeholder={choice === "down" ? "What was wrong or missing?" : "What was useful?"} />
      </label>
      <span className="feedback-count" aria-live="polite">{length}/{MAX_COMMENT}</span>
      <div className="feedback-actions">
        <button type="button" className="btn btn-primary btn-xs" disabled={busy || length > MAX_COMMENT}
          onClick={() => void send()}>Send feedback</button>
        <button type="button" className="btn btn-ghost btn-xs" disabled={busy}
          onClick={() => { setChoice(null); setComment(""); }}>Cancel</button>
      </div>
    </div>}
    {status && <p role="status" className="feedback-status">{status}</p>}
  </section>;
}

function download(name: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: "application/x-ndjson" }));
  const link = document.createElement("a");
  link.href = url; link.download = name;
  document.body.append(link); link.click(); link.remove();
  URL.revokeObjectURL(url);
}

/** Reviewer-only list and JSON Lines export; access is enforced by the API allowlist. */
export function ReviewPage({ client }: { client: FeedbackClient }) {
  const [query, setQuery] = useState<ReviewQuery>({ rating: "down", days: 30 });
  const [items, setItems] = useState<ReviewItem[] | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError("");
    client.review(query, controller.signal).then((result) => {
      if (!controller.signal.aborted) setItems(result);
    }).catch((failure: unknown) => {
      if (controller.signal.aborted) return;
      setItems(null);
      setError(failure instanceof UiFailure && failure.category === "authorization"
        ? "You are not a feedback reviewer." : failureMessage(failure));
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [client, query]);
  async function exportItems() {
    try { download("feedback.jsonl", await client.exportLines(query, new AbortController().signal)); }
    catch (failure) { setError(failureMessage(failure)); }
  }
  return <section aria-label="Feedback review" className="feedback-review">
    <h1>Feedback review</h1>
    <form className="feedback-filters" onSubmit={(event) => event.preventDefault()}>
      <label>Rating <select className="select select-sm" value={query.rating ?? ""}
        onChange={(event) => setQuery({ ...query, rating: (event.target.value || undefined) as Rating | undefined })}>
        <option value="">Any</option><option value="down">Not helpful</option><option value="up">Helpful</option>
      </select></label>
      <label>Type <select className="select select-sm" value={query.targetType ?? ""}
        onChange={(event) => setQuery({ ...query,
          targetType: (event.target.value || undefined) as FeedbackTarget["type"] | undefined })}>
        <option value="">Any</option><option value="briefing">Briefing</option><option value="research">Research answer</option>
      </select></label>
      <label>Last <select className="select select-sm" value={query.days}
        onChange={(event) => setQuery({ ...query, days: Number(event.target.value) })}>
        {[7, 30, 90, 365].map((days) => <option key={days} value={days}>{days} days</option>)}
      </select></label>
      <button type="button" className="btn btn-outline btn-sm" disabled={!items?.length}
        onClick={() => void exportItems()}>Export JSONL</button>
    </form>
    {loading && <p role="status">Loading feedback…</p>}
    {error && <p role="alert">{error}</p>}
    {items && !items.length && !loading && <p role="status">No feedback matches these filters.</p>}
    {items && items.length > 0 && <ul className="feedback-items">
      {items.map((item) => <li key={`${item.target_type}:${item.target_ref}:${item.created_at}`}>
        <p><strong>{labels[item.rating]}</strong> · {item.target_type === "briefing" ? "Briefing" : "Research answer"}
          {" · "}<time dateTime={item.created_at}>{new Date(item.created_at).toLocaleString()}</time></p>
        {typeof item.snapshot?.question === "string" && <p>Question: {item.snapshot.question}</p>}
        <p>{item.comment ?? "No comment."}</p>
        <p className="feedback-ref">Reference: {item.target_ref}</p>
      </li>)}
    </ul>}
  </section>;
}
