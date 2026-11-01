import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import type { Answer, AuthSession, NewsCatalog, NewsItem, Phase, ResearchClient } from "./domain";
import { failureMessage, messages, UiFailure } from "./domain";
import { safeHttps } from "./config";

const phases: Phase[] = ["retrieving", "planning", "synthesizing", "validating"];

export function AnswerView({ answer }: { answer: Answer }) {
  const references = useRef(new Map<number, HTMLLIElement>());
  return <section aria-label="Research answer" className="answer">
    {answer.paragraphs.map((paragraph, index) => <p key={index}>
      {paragraph.text}
      {paragraph.references.map((number, referenceIndex) =>
        <button key={`${number}-${referenceIndex}`} className="btn btn-link btn-xs"
          aria-label={`Focus citation ${number}`}
          onClick={() => references.current.get(number)?.focus()}>[{number}]</button>)}
    </p>)}
    {answer.citations.length > 0 && <>
      <h2>Sources</h2>
      <ol className="citations">
        {answer.citations.map((citation) => <li key={citation.number} tabIndex={-1}
          ref={(element) => {
            if (element) references.current.set(citation.number, element);
            else references.current.delete(citation.number);
          }}>
          [{citation.number}] {citation.href
            ? <a href={citation.href} target="_blank" rel="noopener noreferrer" className="link">
              {citation.host} <span className="sr-only">(opens in a new tab)</span>
            </a> : <span>{citation.url} (unsafe link disabled)</span>}
        </li>)}
      </ol>
    </>}
  </section>;
}

export function App({ auth, research, catalog }: {
  auth: AuthSession; research: ResearchClient; catalog: NewsCatalog;
}) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [phase, setPhase] = useState<Phase | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [signedIn, setSignedIn] = useState(auth.signedIn());
  const [query, setQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [items, setItems] = useState<NewsItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [newsError, setNewsError] = useState("");
  const [authRequired, setAuthRequired] = useState<"news" | "agent" | null>(null);
  const [panelOpen, setPanelOpen] = useState(false);
  const [selected, setSelected] = useState<NewsItem | null>(null);
  const [theme, setTheme] = useState("lofi");
  const current = useRef<AbortController | null>(null);
  const run = useRef(0);
  const newsRun = useRef(0);
  const newsController = useRef<AbortController | null>(null);
  const composer = useRef<HTMLTextAreaElement>(null);
  const agentToggle = useRef<HTMLButtonElement>(null);
  const panelOpener = useRef<HTMLButtonElement | null>(null);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);
  useEffect(() => () => {
    run.current++; current.current?.abort();
    newsRun.current++; newsController.current?.abort();
  }, []);
  useEffect(() => {
    if (panelOpen) composer.current?.focus();
  }, [panelOpen]);
  useEffect(() => {
    if (signedIn) void loadNews("");
    return () => { newsRun.current++; newsController.current?.abort(); newsController.current = null; };
  }, [signedIn, catalog]);

  async function loadNews(search: string) {
    const researchWasActive = current.current !== null;
    const id = ++newsRun.current;
    newsController.current?.abort();
    const controller = new AbortController();
    newsController.current = controller;
    setLoading(true); setLoaded(false); setNewsError(""); setItems([]);
    setSubmittedQuery(search);
    if (!researchWasActive) setAnswer(null);
    try {
      const result = await (search ? catalog.search(search, controller.signal) : catalog.recent(controller.signal));
      if (id !== newsRun.current || controller.signal.aborted) return;
      setItems(result); setLoaded(true);
      if (!current.current && !researchWasActive) setSelected((previous) =>
        previous && result.some((item) => item.id === previous.id) ? previous : null);
    } catch (failure) {
      if (id !== newsRun.current || controller.signal.aborted) return;
      setNewsError(failureMessage(failure));
      if (!current.current && !researchWasActive) setSelected(null);
      if (failure instanceof UiFailure && ["authorization", "interaction"].includes(failure.category))
        setAuthRequired("news");
    } finally {
      if (id === newsRun.current) { setLoading(false); newsController.current = null; }
    }
  }
  async function signIn(resource: "news" | "agent" = "news") {
    setError(""); setQuestion(""); setAnswer(null);
    try { await auth.signIn(resource); setAuthRequired(null); setSignedIn(auth.signedIn()); }
    catch (failure) { setError(failureMessage(failure)); }
  }
  async function signOut() {
    run.current++; current.current?.abort(); setBusy(false);
    newsRun.current++; newsController.current?.abort(); newsController.current = null;
    setItems([]); setSelected(null); setQuery(""); setSubmittedQuery("");
    setNewsError(""); setLoaded(false); setLoading(false); setPanelOpen(false); setAuthRequired(null);
    setQuestion(""); setAnswer(null); setPhase(null); setSignedIn(false); setError("");
    try { await research.stop(); await auth.signOut(); }
    catch (failure) { setError(failureMessage(failure)); }
  }
  async function ask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || current.current) return;
    const controller = new AbortController();
    const id = ++run.current;
    current.current = controller;
    setBusy(true); setError(""); setAnswer(null); setPhase(null);
    try {
      for await (const result of research.ask(question, controller.signal, selected ? [selected.id] : undefined)) {
        if (id !== run.current) return;
        if (result.kind === "progress") setPhase(result.phase);
        else setAnswer(result.answer);
      }
    } catch (failure) {
      if (id === run.current) {
        setError(failureMessage(failure));
        if (failure instanceof UiFailure && ["authorization", "interaction"].includes(failure.category))
          setAuthRequired("agent");
      }
    } finally {
      if (id === run.current) { setBusy(false); current.current = null; }
    }
  }
  async function stop() {
    const id = ++run.current;
    setAnswer(null); setPhase(null);
    try {
      const confirmed = await research.stop();
      if (id === run.current) setError(confirmed ? "The agent confirmed cancellation." : messages.stopped);
    } catch {
      if (id === run.current) setError(messages.stopped);
    } finally {
      current.current?.abort();
      if (id === run.current) { setBusy(false); current.current = null; }
    }
  }
  function openPanel(opener: HTMLButtonElement, item?: NewsItem) {
    if (!busy && item) {
      setSelected(item);
      setQuestion(""); setAnswer(null); setError("");
    }
    panelOpener.current = opener;
    setPanelOpen(true);
    composer.current?.focus();
  }
  function closePanel() {
    setPanelOpen(false);
    const opener = panelOpener.current;
    (opener && !opener.disabled ? opener : agentToggle.current)?.focus();
  }
  return <>
    <a href="#main" className="skip-link">Skip to news</a>
    <header className="navbar site-header">
      <a href="/" className="brand" aria-label="Newsloom home">Newsloom<span className="brand-dot">.</span></a>
      <span className="badge badge-outline">Early access</span>
      {signedIn && <form className="top-search" role="search" onSubmit={(event) => {
        event.preventDefault();
        if (!newsController.current) void loadNews(query.trim());
      }}>
        <label htmlFor="news-search" className="sr-only">Search stored news</label>
        <input id="news-search" type="search" className="input" value={query}
          placeholder="Search stored news..." onChange={(event) => setQuery(event.target.value)} />
        <button type="submit" className="btn btn-primary btn-sm" disabled={loading}>Search</button>
      </form>}
      <div className="header-actions">
        {signedIn && <button ref={agentToggle} className="btn btn-outline btn-sm"
          aria-controls="agent-panel" aria-expanded={panelOpen}
          onClick={(event) => panelOpen ? closePanel() : openPanel(event.currentTarget)}>
          {busy ? "Agent (working)" : "Agent"}
        </button>}
        <button className="btn btn-ghost btn-sm" aria-label={`Switch to ${theme === "lofi" ? "dark" : "lofi"} theme`}
          onClick={() => setTheme(theme === "lofi" ? "dark" : "lofi")}>Theme</button>
        {signedIn ? <button className="btn btn-outline btn-sm" onClick={() => void signOut()}>Sign out</button>
          : <button className="btn btn-primary btn-sm" onClick={() => void signIn()}>Sign in</button>}
      </div>
    </header>
    <main id="main" className={`news-page ${panelOpen ? "with-agent" : ""}`}>
      <section className="news-column">
      <div className="news-heading">
        <div>
          <div className="eyebrow">STORED NEWS. CLEARER CONTEXT.</div>
          <h1>{submittedQuery ? "Search results" : "Latest news"}</h1>
          <p className="intro">{submittedQuery
            ? `Ranked by relevance · Up to 20 results for "${submittedQuery}"`
            : "The latest 20 stored articles, newest first."}</p>
        </div>
        {signedIn && (submittedQuery
          ? <button className="btn btn-outline btn-sm" disabled={loading} onClick={() => {
            setQuery(""); void loadNews("");
          }}>Clear search</button>
          : <button className="btn btn-outline btn-sm" disabled={loading} onClick={() => void loadNews("")}>Refresh</button>)}
      </div>
      {!signedIn ? <section className="card signin-card">
        <h2>Your news, with context</h2><p>Sign in with your organization account to browse stored news and optionally ask the agent for more detail.</p>
        <button className="btn btn-primary" onClick={() => void signIn()}>Sign in to read news</button>
      </section> : <>
        {loading && <p role="status" aria-live="polite">Loading stored news...</p>}
        {newsError && <div className="alert alert-error" role="alert">{newsError}</div>}
        {loaded && !items.length && <p role="status">{submittedQuery ? "No news matches this search." : "No stored news yet."}</p>}
        <div className="news-list">
          {items.map((item) => {
            const link = safeHttps(item.url);
            return <article className="card news-card" key={item.id}>
              <div className="news-meta"><span>{item.source} · {item.category}</span>
                <time dateTime={item.publishedAt}>{new Date(item.publishedAt).toLocaleString()}</time></div>
              <h2>{item.title}</h2><p className="news-summary">{item.summary}</p>
              <div className="news-actions">
                {link ? <a href={link.href} className="link" target="_blank" rel="noopener noreferrer">
                  Open original · {link.hostname}<span className="sr-only"> (opens in a new tab)</span>
                </a> : <span>Original link unavailable</span>}
                <button className="btn btn-outline btn-sm" disabled={busy}
                  onClick={(event) => openPanel(event.currentTarget, item)}
                  aria-label={`Ask about this: ${item.title}`}>Ask about this</button>
              </div>
            </article>;
          })}
        </div>
      </>}
      </section>
      {signedIn && <aside id="agent-panel" className="agent-panel" aria-label="Agent interactions"
        tabIndex={0} hidden={!panelOpen}>
        <div className="panel-heading"><h2>Ask Newsloom</h2>
          <button className="btn btn-ghost btn-sm" onClick={closePanel}>Close agent panel</button></div>
        <p className="notice">Research is early access. Quality evaluation is still in progress.</p>
        {selected && <div className="context-chip">
          <span>Current news: {selected.title}</span>
          <button className="btn btn-ghost btn-xs" disabled={busy} aria-label="Remove news context"
            onClick={() => { setSelected(null); setAnswer(null); }}>Remove</button>
        </div>}
        {!selected && <p className="context-note">General research · No news item selected</p>}
        <form onSubmit={(event) => void ask(event)}>
          <label htmlFor="question" className="composer-label">What would you like to understand?</label>
          <textarea ref={composer} id="question" className="textarea" rows={4} value={question} disabled={busy}
            placeholder="Ask about recent announcements, differences, or trends..."
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); }
            }} aria-describedby="question-help" />
          <div className="composer-footer">
            <p id="question-help">Each question is independent. Stored summaries and metadata only.</p>
            {busy ? <button type="button" className="btn btn-outline" onClick={() => void stop()}>Stop</button>
              : <button className="btn btn-primary" type="submit" disabled={!question.trim()}>Ask Newsloom</button>}
          </div>
        </form>
        {busy && <div aria-live="polite" role="status" className="progress-area">
          <span className="loading loading-spinner loading-sm" aria-hidden="true" />
          {phase ? `${phase.charAt(0).toUpperCase()}${phase.slice(1)}` : "Connecting to the agent"}
          <div className="phase-labels" aria-hidden="true">
            {phases.map((value) => <span key={value} className={value === phase ? "active-phase" : ""}>{value}</span>)}
          </div>
        </div>}
        {answer && <AnswerView answer={answer} />}
      </aside>}
      {authRequired && <div className="alert" role="alert">
        <span>Sign-in is required for {authRequired === "news" ? "news access" : "research"}.</span>
        <button className="btn btn-outline btn-sm" onClick={() => void signIn(authRequired)}>
          Sign in for {authRequired === "news" ? "news" : "research"}</button>
      </div>}
      {error && <div className="alert alert-error error-notice" role="alert">{error}</div>}
      <footer className="page-footer">No web search. No saved conversations. Citations link to the original reporting.</footer>
    </main>
  </>;
}
