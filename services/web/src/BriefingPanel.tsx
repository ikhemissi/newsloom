import { useEffect, useRef, useState } from "react";
import type { Briefing, BriefingParagraph, BriefingResponse, NewsCatalog } from "./domain";
import { failureMessage } from "./domain";
import { safeHttps } from "./config";
import { briefingWordCount } from "./briefing";
import { LocalTimestamp, localDateTimeFormat, useDisplayClock } from "./timestamps";
import type { FeedbackClient } from "./feedback";
import { FeedbackControls } from "./Feedback";

const minute = 60_000;

function PublishedBriefing({ briefing }: { briefing: Briefing }) {
  const references = useRef(new Map<number, HTMLLIElement>());
  function paragraph(part: BriefingParagraph, key?: number) {
    return <p key={key}>{part.text}{part.references.map((number, index) =>
      <button key={`${number}-${index}`} type="button" className="btn btn-link btn-xs"
        aria-label={`Focus briefing citation ${number}`}
        onClick={() => references.current.get(number)?.focus()}>[{number}]</button>)}</p>;
  }
  const minutes = Math.ceil(briefingWordCount(briefing) / 200);
  return <>
    {briefing.coverage === "empty" ? <p>No stored news was available in this seven-day window.</p>
      : briefing.coverage === "no_material_changes"
        ? <p>No material changes were identified in reviewed stored reporting.</p> : <>
      {briefing.coverage === "limited" && <p>Limited evidence: a shorter overview, without padding.</p>}
      <div className="briefing-tldr"><h4>TL;DR</h4>
        {briefing.tldr && <p>{briefing.tldr.text}{briefing.tldr.references.map((number, index) =>
          <span key={`${number}-${index}`}> [{number}]</span>)}</p>}
      </div>
      <details className="briefing-details">
        <summary>Full briefing and sources · About {minutes} {minutes === 1 ? "minute" : "minutes"}</summary>
        {briefing.sections.map((section, index) => <section key={index} aria-label={section.heading}>
          <h4>{section.heading}</h4>
          {section.paragraphs.map((part, partIndex) => paragraph(part, partIndex))}
        </section>)}
        <h4>Briefing sources</h4>
        <ol className="briefing-citations">{briefing.citations.map((citation) => {
          const href = safeHttps(citation.url)?.href;
          return <li key={citation.number} tabIndex={-1} ref={(element) => {
            if (element) references.current.set(citation.number, element);
            else references.current.delete(citation.number);
          }}>
            [{citation.number}] {href
              ? <a href={href} target="_blank" rel="noopener noreferrer" className="link">
                {citation.title} ({safeHttps(citation.url)?.host})
                <span className="sr-only"> (opens in a new tab)</span>
              </a> : <span>{citation.title} (unsafe link disabled)</span>}
          </li>;
        })}</ol>
      </details>
    </>}
  </>;
}

export function BriefingPanel({ catalog, active, feedback }: {
  catalog: NewsCatalog; active: boolean; feedback?: FeedbackClient | undefined;
}) {
  const [data, setData] = useState<BriefingResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [retry, setRetry] = useState(0);
  const [retryQueued, setRetryQueued] = useState(false);
  const lastRead = useRef<number | null>(null);
  useDisplayClock(active);
  const formatter = localDateTimeFormat();
  useEffect(() => {
    // A different catalogue represents a different session/data boundary.
    lastRead.current = null; setData(null); setError(""); setRetryQueued(false);
  }, [catalog]);
  useEffect(() => {
    if (!active) return;
    let disposed = false;
    let controller: AbortController | null = null;
    let timer: ReturnType<typeof setTimeout>;
    async function read() {
      if (disposed || controller) return;
      clearTimeout(timer);
      const remaining = lastRead.current === null ? 0 : Math.max(0, minute - (Date.now() - lastRead.current));
      if (remaining > 0) { timer = setTimeout(() => void read(), remaining); return; }
      if (document.visibilityState === "hidden") return;
      lastRead.current = Date.now();
      const owned = new AbortController();
      controller = owned;
      setLoading(true); setRetryQueued(false);
      try {
        const result = await catalog.briefing(owned.signal);
        if (!disposed && !owned.signal.aborted) { setData(result); setError(""); }
      } catch (failure) {
        if (!disposed && !owned.signal.aborted) setError(failureMessage(failure));
      } finally {
        if (!disposed) {
          controller = null; setLoading(false);
          timer = setTimeout(() => void read(), Math.max(0, minute - (Date.now() - (lastRead.current ?? 0))));
        }
      }
    }
    const resume = () => { if (document.visibilityState === "visible") void read(); };
    void read();
    window.addEventListener("focus", resume);
    document.addEventListener("visibilitychange", resume);
    return () => {
      disposed = true; controller?.abort(); clearTimeout(timer);
      setLoading(false);
      window.removeEventListener("focus", resume);
      document.removeEventListener("visibilitychange", resume);
    };
  }, [active, catalog, retry]);
  const artifact = data?.briefing;
  return <section aria-label="Daily news briefing" className="daily-briefing">
    <h3>Daily news briefing</h3>
    {loading && active && !data && <p role="status">Reading the published briefing…</p>}
    {error && <div role="alert">
      <p>Briefing read failed. {error}</p>
      {artifact && <p>Showing the last publication; freshness could not be checked.</p>}
      <button type="button" className="btn btn-outline btn-sm" disabled={loading}
        onClick={() => { setRetryQueued(true); setRetry((value) => value + 1); }}>Retry briefing</button>
      {retryQueued && <p role="status">Retry scheduled for the next permitted read.</p>}
    </div>}
    {data && <>
      {!artifact && <p role="status">No published briefing is available yet.
        {data.refresh.state === "failed" && " Briefing refresh failed."}</p>}
      {artifact && !error && (data.refresh.stale || data.refresh.state === "failed") && <p role="status">
        {data.refresh.stale && "This briefing is stale."}
        {data.refresh.state === "failed" && " Briefing refresh failed."}
      </p>}
      {artifact && <>
        <p className="briefing-note">Generated: <LocalTimestamp value={artifact.generated_at} formatter={formatter} /></p>
        <PublishedBriefing key={artifact.version} briefing={artifact} />
        {feedback && <FeedbackControls client={feedback} label="Rate this briefing"
          target={{ type: "briefing", ref: artifact.version }} />}
      </>}
    </>}
    {!data && !error && !loading && <p role="status">{active
      ? "Waiting for the next permitted briefing read (at most once per minute)."
      : "The shared briefing will be read when this panel opens."}</p>}
  </section>;
}
