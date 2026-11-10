import { useEffect, useRef, useState } from "react";
import type { FormEvent, KeyboardEvent } from "react";
import type { Answer, AuthSession, NewsCatalog, NewsDetail, NewsItem, Phase, ResearchClient, SourceCatalog } from "./domain";
import { failureMessage, messages, UiFailure } from "./domain";
import { safeHttps } from "./config";
import { buildFilters, emptyDraft, emptySnapshot } from "./filters";
import type { DatePeriod, FilterDraft, FilterSnapshot } from "./filters";
import { newsRoute } from "./navigation";
import type { NewsRoute } from "./navigation";
import { LocalTimestamp, localDateTimeFormat, useDisplayClock } from "./timestamps";
import { BriefingPanel } from "./BriefingPanel";
import { readOnlyLine, useReadOnly } from "./readOnly";
import { clearThread, historyFor, loadThread, saveThread } from "./conversation";
import type { Turn } from "./conversation";
import type { FeedbackClient, ResearchSnapshot } from "./feedback";
import { FeedbackControls, ReviewPage } from "./Feedback";
import type { RadarCard, RadarClient } from "./radar";
import { ProductPage, RadarPage, StackPage } from "./Radar";

const STATUS: Record<string, string> = {
  announced: "Announced", preview: "Preview", ga: "GA", updated: "Updated",
  deprecated: "Deprecated", retired: "Retired",
};
const phases: Phase[] = ["retrieving", "planning", "synthesizing", "validating"];
const periods: { value: DatePeriod; label: string }[] = [
  { value: "any", label: "Any time" }, { value: "today", label: "Today" },
  { value: "7days", label: "Last 7 days" }, { value: "30days", label: "Last 30 days" },
  { value: "custom", label: "Custom dates" },
];

function FilterChips({ snapshot }: { snapshot: FilterSnapshot }) {
  return <ul className="filter-chips">{snapshot.labels.map((label, index) =>
    <li key={index} className="badge badge-outline">{label}</li>)}</ul>;
}

export function AnswerView({ answer, label = "Research answer" }: { answer: Answer; label?: string }) {
  const references = useRef(new Map<number, HTMLLIElement>());
  return <section aria-label={label} className="answer">
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

export function App({ auth, research, catalog, feedback, radar }: {
  auth: AuthSession; research: ResearchClient; catalog: NewsCatalog; feedback?: FeedbackClient | undefined;
  radar?: RadarClient | undefined;
}) {
  const listPath = radar ? "/news" : "/";
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<Turn[]>(() => loadThread());
  const [pending, setPending] = useState("");
  const [researchError, setResearchError] = useState("");
  const latestTurn = useRef<HTMLLIElement | null>(null);
  const [rated, setRated] = useState<{ id: string; snapshot: ResearchSnapshot } | null>(null);
  const [phase, setPhase] = useState<Phase | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [signedIn, setSignedIn] = useState(auth.signedIn());
  const now = useDisplayClock(signedIn);
  const dateTimeFormatter = localDateTimeFormat();
  const [query, setQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [draft, setDraft] = useState<FilterDraft>({ ...emptyDraft });
  const [applied, setApplied] = useState<FilterSnapshot>(emptySnapshot);
  const [choices, setChoices] = useState<SourceCatalog | null>(null);
  const [choicesLoading, setChoicesLoading] = useState(false);
  const [choicesError, setChoicesError] = useState("");
  const [submittedContext, setSubmittedContext] = useState<{ item: NewsItem | null; snapshot: FilterSnapshot } | null>(null);
  const [items, setItems] = useState<NewsItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [appending, setAppending] = useState(false);
  const [appendError, setAppendError] = useState("");
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [readAt, setReadAt] = useState("");
  const [readAge, setReadAge] = useState(0);
  const [route, setRoute] = useState<NewsRoute>(() => newsRoute(window.location.pathname, !!radar));
  const [detail, setDetail] = useState<NewsDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [detailLoaded, setDetailLoaded] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [newsError, setNewsError] = useState("");
  const [authRequired, setAuthRequired] = useState<"news" | "agent" | null>(null);
  const [panelOpen, setPanelOpen] = useState(false);
  useEffect(() => { saveThread(turns); }, [turns]);
  const closePanelRef = useRef<() => void>(() => undefined);
  useEffect(() => {
    if (!panelOpen) return;
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); closePanelRef.current(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [panelOpen]);
  useEffect(() => { latestTurn.current?.scrollIntoView?.({ block: "nearest" }); }, [turns.length]);
  const readOnlyAsOf = useReadOnly();
  useEffect(() => {
    document.documentElement.classList.toggle("read-only", readOnlyAsOf !== null);
    if (readOnlyAsOf !== null) setPanelOpen(false);
  }, [readOnlyAsOf]);
  const [selected, setSelected] = useState<NewsItem | null>(null);
  const [theme, setTheme] = useState("lofi");
  const current = useRef<AbortController | null>(null);
  const run = useRef(0);
  const newsRun = useRef(0);
  const newsController = useRef<AbortController | null>(null);
  const choicesRun = useRef(0);
  const choicesController = useRef<AbortController | null>(null);
  const detailRun = useRef(0);
  const detailController = useRef<AbortController | null>(null);
  const acceptedCursors = useRef(new Set<string>());
  const browseStarted = useRef(false);
  const browseScroll = useRef(0);
  const detailOpener = useRef<HTMLElement | null>(null);
  const newsHeading = useRef<HTMLHeadingElement>(null);
  const detailHeading = useRef<HTMLHeadingElement>(null);
  const composer = useRef<HTMLTextAreaElement>(null);
  const agentToggle = useRef<HTMLButtonElement>(null);
  const panelOpener = useRef<HTMLButtonElement | null>(null);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);
  useEffect(() => () => {
    run.current++; current.current?.abort();
    newsRun.current++; newsController.current?.abort();
    choicesRun.current++; choicesController.current?.abort();
    detailRun.current++; detailController.current?.abort();
  }, []);
  useEffect(() => {
    const changed = () => setRoute(newsRoute(window.location.pathname, !!radar));
    window.addEventListener("popstate", changed);
    return () => window.removeEventListener("popstate", changed);
  }, []);
  useEffect(() => {
    if (panelOpen) composer.current?.focus();
  }, [panelOpen]);
  useEffect(() => {
    if (signedIn) { browseStarted.current = false; void loadSources(); }
    return () => {
      newsRun.current++; newsController.current?.abort(); newsController.current = null;
      choicesRun.current++; choicesController.current?.abort(); choicesController.current = null;
    };
  }, [signedIn, catalog]);
  useEffect(() => {
    if (!signedIn) return;
    if (route.kind === "news") {
      if (!browseStarted.current) void loadNews("", emptySnapshot);
      else {
        (detailOpener.current?.isConnected ? detailOpener.current : newsHeading.current)?.focus({ preventScroll: true });
        window.scrollTo({ top: browseScroll.current, behavior: "instant" });
      }
    } else if (route.kind === "detail") {
      void loadDetail(route.id);
      window.scrollTo({ top: 0, behavior: "instant" });
    }
    return () => { detailRun.current++; detailController.current?.abort(); detailController.current = null; };
  }, [route, signedIn, catalog]);
  useEffect(() => {
    if (route.kind === "detail" && !detailLoading) detailHeading.current?.focus({ preventScroll: true });
  }, [route, detailLoading]);

  function navigateHome(replace = false) {
    window.history[replace ? "replaceState" : "pushState"](null, "", listPath);
    setRoute({ kind: "news" });
  }
  function navigate(path: string, event?: React.MouseEvent<HTMLAnchorElement>) {
    if (event && (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey)) return;
    event?.preventDefault();
    window.history.pushState(null, "", path);
    setRoute(newsRoute(path, !!radar));
    window.scrollTo({ top: 0, behavior: "instant" });
  }
  function askAboutCard(card: RadarCard, opener: HTMLButtonElement) {
    openPanel(opener, { id: card.newsId, title: card.title, summary: card.statement, source: card.source,
      category: "", publishedAt: card.publishedAt, url: card.url });
  }
  function openDetail(event: React.MouseEvent<HTMLAnchorElement>, id: string) {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    browseScroll.current = window.scrollY;
    detailOpener.current = event.currentTarget;
    window.history.pushState({ newsloomDetail: true }, "", `/news/${id}`);
    setRoute({ kind: "detail", id });
  }
  function backToNews() {
    if (browseStarted.current && window.history.state?.newsloomDetail === true) window.history.back();
    else navigateHome(true);
  }
  async function loadDetail(id: string) {
    const runId = ++detailRun.current;
    detailController.current?.abort();
    const controller = new AbortController();
    detailController.current = controller;
    setDetail(null); setDetailLoaded(false); setDetailError(""); setDetailLoading(true);
    try {
      const result = await catalog.detail(id, controller.signal);
      if (runId === detailRun.current && !controller.signal.aborted) { setDetail(result); setDetailLoaded(true); }
    } catch (failure) {
      if (runId === detailRun.current && !controller.signal.aborted) {
        setDetailError(failureMessage(failure));
        if (failure instanceof UiFailure && ["authorization", "interaction"].includes(failure.category))
          setAuthRequired("news");
      }
    } finally {
      if (runId === detailRun.current) { setDetailLoading(false); detailController.current = null; }
    }
  }

  async function loadSources() {
    const id = ++choicesRun.current;
    choicesController.current?.abort();
    const controller = new AbortController();
    choicesController.current = controller;
    setChoicesLoading(true); setChoicesError("");
    try {
      const result = await catalog.sources(controller.signal);
      if (id === choicesRun.current && !controller.signal.aborted) setChoices(result);
    } catch (failure) {
      if (id === choicesRun.current && !controller.signal.aborted) {
        setChoicesError(failureMessage(failure));
        if (failure instanceof UiFailure && ["authorization", "interaction"].includes(failure.category))
          setAuthRequired("news");
      }
    } finally {
      if (id === choicesRun.current) { setChoicesLoading(false); choicesController.current = null; }
    }
  }
  async function loadNews(search: string, snapshot: FilterSnapshot = applied) {
    browseStarted.current = true;
    browseScroll.current = 0;
    if (route.kind !== "news") navigateHome();
    const researchWasActive = current.current !== null;
    const id = ++newsRun.current;
    newsController.current?.abort();
    const controller = new AbortController();
    newsController.current = controller;
    setLoading(true); setAppendedReset();
    setLoaded(false); setNewsError(""); setItems([]);
    setSubmittedQuery(search);
    setApplied(snapshot);
    try {
      const result = await (search || Object.keys(snapshot.filters).length
        ? catalog.search(search || undefined, controller.signal, snapshot.filters) : catalog.recent(controller.signal));
      if (id !== newsRun.current || controller.signal.aborted) return;
      setItems(result.items); setNextCursor(result.nextCursor); setReadAt(result.readAt); setReadAge(result.cacheAgeSeconds); setLoaded(true);
      if (!current.current && !researchWasActive) setSelected((previous) =>
        previous && result.items.some((item) => item.id === previous.id) ? previous : null);
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
  function setAppendedReset() {
    setAppending(false); setAppendError(""); setNextCursor(null); setReadAt(""); setReadAge(0);
    acceptedCursors.current.clear();
  }
  async function loadMore() {
    if (newsController.current || submittedQuery || !nextCursor || items.length >= 200) return;
    const id = ++newsRun.current, cursor = nextCursor;
    const controller = new AbortController();
    newsController.current = controller;
    setAppending(true); setAppendError("");
    try {
      const result = await catalog.search(undefined, controller.signal, applied.filters, cursor);
      if (id !== newsRun.current || controller.signal.aborted) return;
      if (result.nextCursor === cursor || (result.nextCursor && acceptedCursors.current.has(result.nextCursor)))
        throw new UiFailure("invalid_response");
      acceptedCursors.current.add(cursor);
      setItems((previous) => {
        const ids = new Set(previous.map((item) => item.id));
        return [...previous, ...result.items.filter((item) => !ids.has(item.id))].slice(0, 200);
      });
      setNextCursor(result.nextCursor); setReadAt(result.readAt); setReadAge(result.cacheAgeSeconds);
    } catch (failure) {
      if (id === newsRun.current && !controller.signal.aborted) {
        setAppendError(failureMessage(failure));
        if (failure instanceof UiFailure && ["authorization", "interaction"].includes(failure.category))
          setAuthRequired("news");
      }
    } finally {
      if (id === newsRun.current) { setAppending(false); newsController.current = null; }
    }
  }
  function applyFilters(search: string) {
    if (newsController.current && !appending) return;
    try { void loadNews(search, buildFilters(draft, choices)); }
    catch (failure) { setNewsError(failureMessage(failure)); }
  }
  async function signIn(resource: "news" | "agent" = "news") {
    setError(""); setQuestion(""); setSubmittedContext(null);
    try { await auth.signIn(resource); setAuthRequired(null); setSignedIn(auth.signedIn()); }
    catch (failure) { setError(failureMessage(failure)); }
  }
  async function signOut() {
    run.current++; current.current?.abort(); current.current = null; setBusy(false);
    newsRun.current++; newsController.current?.abort(); newsController.current = null;
    setItems([]); setSelected(null); setQuery(""); setSubmittedQuery("");
    choicesRun.current++; choicesController.current?.abort(); choicesController.current = null;
    detailRun.current++; detailController.current?.abort(); detailController.current = null;
    setDetail(null); setDetailError(""); setDetailLoading(false); setDetailLoaded(false);
    setAppendedReset(); browseStarted.current = false; browseScroll.current = 0;
    detailOpener.current = null; navigateHome(true);
    setChoices(null); setChoicesError(""); setChoicesLoading(false);
    setDraft({ ...emptyDraft }); setApplied(emptySnapshot); setSubmittedContext(null);
    setNewsError(""); setLoaded(false); setLoading(false); setPanelOpen(false); setAuthRequired(null);
    setQuestion(""); setTurns([]); clearThread(); setRated(null); setPending(""); setResearchError("");
    setPhase(null); setSignedIn(false); setError("");
    try { await research.stop(); await auth.signOut(); }
    catch (failure) { setError(failureMessage(failure)); }
  }
  async function ask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await send(question);
  }
  async function send(value: string) {
    if (busy || current.current || !value.trim()) return;
    const controller = new AbortController();
    const id = ++run.current;
    current.current = controller;
    setBusy(true); setResearchError(""); setPhase(null); setPending(value); setQuestion("");
    const context = { item: selected, snapshot: applied };
    setSubmittedContext(context);
    const history = historyFor(turns);
    try {
      for await (const result of research.ask(value, controller.signal,
        context.item ? [context.item.id] : undefined, context.snapshot.filters, history)) {
        if (id !== run.current) return;
        if (result.kind === "progress") setPhase(result.phase);
        else {
          const turn: Turn = { id: crypto.randomUUID(), question: value, text: result.text, answer: result.answer,
            followUps: result.conversation.followUps, citedItemIds: result.conversation.citedItemIds };
          setTurns((previous) => [...previous, turn]);
          setRated({ id: turn.id, snapshot: {
            question: value, answer: { paragraphs: result.answer.paragraphs },
            citations: result.answer.citations.map(({ number, url }) => ({ number, url })),
            filters: { ...context.snapshot.filters, ...(context.item ? { item_id: context.item.id } : {}) },
          } });
        }
      }
    } catch (failure) {
      if (id === run.current) {
        setResearchError(failureMessage(failure));
        setQuestion((current) => current || value);
        if (failure instanceof UiFailure && ["authorization", "interaction"].includes(failure.category))
          setAuthRequired("agent");
      }
    } finally {
      if (id === run.current) { setBusy(false); setPending(""); current.current = null; }
    }
  }
  function trapSheetFocus(event: KeyboardEvent<HTMLElement>) {
    if (event.key !== "Tab" || !window.matchMedia?.("(max-width: 1000px)").matches) return;
    const focusable = [...event.currentTarget.querySelectorAll<HTMLElement>(
      "button:not([disabled]), a[href], textarea:not([disabled]), input:not([disabled])")]
      .filter((element) => element.getClientRects().length > 0);
    const first = focusable[0], last = focusable[focusable.length - 1];
    if (!first || !last) return;
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }
  function newConversation() {
    setTurns([]); clearThread(); setRated(null); setSubmittedContext(null); setResearchError("");
    composer.current?.focus();
  }
  async function stop() {
    const id = ++run.current;
    setPending(""); setPhase(null);
    try {
      const confirmed = await research.stop();
      if (id === run.current) setResearchError(confirmed ? "The agent confirmed cancellation." : messages.stopped);
    } catch {
      if (id === run.current) setResearchError(messages.stopped);
    } finally {
      current.current?.abort();
      if (id === run.current) { setBusy(false); current.current = null; }
    }
  }
  function openPanel(opener: HTMLButtonElement, item?: NewsItem) {
    if (!busy && item) {
      setSelected(item);
      setQuestion(""); setError("");
    }
    panelOpener.current = opener;
    setPanelOpen(true);
    composer.current?.focus();
  }
  closePanelRef.current = closePanel;
  function closePanel() {
    setPanelOpen(false);
    const opener = panelOpener.current;
    (opener?.isConnected && !opener.disabled ? opener : agentToggle.current)?.focus();
  }
  return <>
    <a href="#main" className="skip-link">Skip to news</a>
    <header className="navbar site-header">
      <a href="/" className="brand" aria-label="Newsloom home">Newsloom<span className="brand-dot">.</span></a>
      <span className="badge badge-outline">Early access</span>
      {signedIn && radar && <nav aria-label="Sections" className="site-nav">
        {([["/", "Radar", "radar"], ["/news", "All news", "news"], ["/stack", "My stack", "stack"]] as const).map(([path, text, kind]) =>
          <a key={path} href={path} className={`link ${route.kind === kind ? "active" : ""}`}
            aria-current={route.kind === kind ? "page" : undefined} onClick={(event) => navigate(path, event)}>{text}</a>)}
      </nav>}
      {signedIn && <form className="top-search" role="search" data-write onSubmit={(event) => {
        event.preventDefault();
        applyFilters(query.trim());
      }}>
        <label htmlFor="news-search" className="sr-only">Search stored news</label>
        <input id="news-search" type="search" className="input" value={query}
          placeholder="Search stored news..." onChange={(event) => setQuery(event.target.value)} />
        <button type="submit" className="btn btn-primary btn-sm" disabled={loading}>Search</button>
      </form>}
      <div className="header-actions">
        {signedIn && <button ref={agentToggle} className="btn btn-outline btn-sm" data-write
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
    {readOnlyAsOf && <p className="read-only-line" role="status">{readOnlyLine(readOnlyAsOf)}</p>}
    <main id="main" className={`news-page ${panelOpen ? "with-agent" : ""}`}>
      <section className="news-column">
      {signedIn && radar && route.kind === "radar" && <RadarPage client={radar} navigate={navigate}
        onAsk={askAboutCard} briefing={<BriefingPanel catalog={catalog} active={signedIn} feedback={feedback} />} />}
      {signedIn && radar && route.kind === "product" && <ProductPage client={radar} id={route.id}
        navigate={navigate} onBack={() => window.history.back()} />}
      {signedIn && radar && route.kind === "stack" && <StackPage client={radar} navigate={navigate} />}
      {signedIn && route.kind === "feedback" && (feedback ? <ReviewPage client={feedback} />
        : <section><h1>Feedback review</h1><p>Feedback is not available.</p></section>)}
      {signedIn && route.kind === "invalid" && <section>
        <h1>Invalid news link</h1><p>This page does not identify a stored news item.</p>
        <button className="btn btn-outline" onClick={() => navigateHome(true)}>Back to news</button>
      </section>}
      {signedIn && route.kind === "detail" && <section aria-label="News detail">
        <button className="btn btn-outline btn-sm" onClick={backToNews}>Back to news</button>
        <h1 ref={detailHeading} tabIndex={-1}>{detail?.title ?? "News detail"}</h1>
        {detailLoading && <p role="status">Loading stored news detail...</p>}
        {detailError && <div role="alert" className="alert alert-error">
          <span>{detailError}</span><button className="btn btn-outline btn-sm" onClick={() => void loadDetail(route.id)}>Retry detail</button>
        </div>}
        {detailLoaded && !detail && <p role="status">This stored news item was not found.</p>}
        {detail && <>
          <p>{detail.source} · {detail.category}</p>
          <LocalTimestamp value={detail.publishedAt} formatter={dateTimeFormatter} now={now} />
          <p className="news-summary">{detail.summary}</p>
          {!!detail.announcements?.length && <ul className="announcements" aria-label="Announcements">
            {detail.announcements.map((entry, index) => <li key={index}>
              {entry.status !== "none" && <span className="badge badge-ghost badge-sm">{STATUS[entry.status] ?? entry.status}</span>}{" "}
              {entry.statement}
              {entry.deadline && <> <strong>By {entry.deadline}</strong></>}
            </li>)}
          </ul>}
          <dl className="detail-metadata">
            <dt>Author</dt><dd>{detail.author || "Not supplied"}</dd>
            <dt>Date origin</dt><dd>{detail.dateOrigin}</dd>
            <dt>Publisher categories</dt><dd>{detail.publisherCategories.join(", ") || "Not supplied"}</dd>
            <dt>Tags</dt><dd>{detail.tags.join(", ")}</dd>
          </dl>
          <p className="notice">Stored summary and metadata only. The full article is available at its original source.</p>
          <div className="news-actions">
            {safeHttps(detail.url) ? <a href={detail.url} target="_blank" rel="noopener noreferrer" className="link">Open original</a>
              : <span>Original link unavailable</span>}
            <button className="btn btn-outline btn-sm" disabled={busy} data-write
              onClick={(event) => openPanel(event.currentTarget, detail)}
              aria-label={`Ask about this: ${detail.title}`}>Ask about this</button>
          </div>
        </>}
      </section>}
      <div hidden={signedIn && route.kind !== "news"}>
      <h1 className="sr-only" ref={newsHeading} tabIndex={-1}>{submittedQuery ? "Search results" : Object.keys(applied.filters).length ? "Filtered news" : "Latest news"}</h1>
      {!signedIn ? <section className="card signin-card">
        <h2>Your news, with context</h2><p>Sign in with your organization account to browse stored news and optionally ask the agent for more detail.</p>
        <button className="btn btn-primary" onClick={() => void signIn()}>Sign in to read news</button>
      </section> : <>
        <form aria-label="News filters" className="filter-bar" onSubmit={(event) => {
          event.preventDefault(); applyFilters(submittedQuery);
        }}>
          <label><span id="filter-source-label">Source</span>
            <select aria-labelledby="filter-source-label" className="select" value={draft.source} disabled={!choices || choicesLoading || !!choicesError}
              onChange={(event) => setDraft({ ...draft, source: event.target.value })}>
              <option value="">Any source</option>
              {choices?.sources.map((source) => <option key={source.id} value={source.id}>{source.id}</option>)}
            </select>
          </label>
          <label><span id="filter-category-label">Category</span>
            <select aria-labelledby="filter-category-label" className="select" value={draft.category} disabled={!choices || choicesLoading || !!choicesError}
              onChange={(event) => setDraft({ ...draft, category: event.target.value })}>
              <option value="">Any category</option>
              {choices?.categories.map((category) => <option key={category.id} value={category.id}>{category.label}</option>)}
            </select>
          </label>
          <label><span id="filter-period-label">Date period</span>
            <select aria-labelledby="filter-period-label" className="select" value={draft.period} onChange={(event) => {
              const period = periods.find((value) => value.value === event.target.value);
              if (period) setDraft({ ...draft, period: period.value });
              else setNewsError(messages.invalid_filters);
            }}>
              {periods.map((period) => <option key={period.value} value={period.value}>{period.label}</option>)}
            </select>
          </label>
          {draft.period === "custom" && <>
            <label>Start date<input className="input" type="date" value={draft.start}
              onChange={(event) => setDraft({ ...draft, start: event.target.value })} /></label>
            <label>End date<input className="input" type="date" value={draft.end}
              onChange={(event) => setDraft({ ...draft, end: event.target.value })} /></label>
          </>}
          <button className="btn btn-outline btn-sm" disabled={loading}>Apply filters</button>
          <button type="button" className="btn btn-ghost btn-sm" disabled={loading} onClick={() => {
            setDraft({ ...emptyDraft }); void loadNews(submittedQuery, emptySnapshot);
          }}>Reset filters</button>
          {submittedQuery
            ? <button type="button" className="btn btn-outline btn-sm" disabled={loading} onClick={() => {
              setQuery(""); void loadNews("");
            }}>Clear search</button>
            : <button type="button" className="btn btn-outline btn-sm" disabled={loading} onClick={() => void loadNews("")}>Refresh</button>}
          <p className="filter-help">Dates are inclusive calendar dates in your local timezone. Changes apply only on Apply or Search.</p>
        </form>
        {submittedQuery && <p className="news-search-context">Ranked by relevance · Up to 20 results for "{submittedQuery}"</p>}
        {choicesLoading && <p role="status">Loading source/category choices...</p>}
        {choicesError && <div role="alert" className="alert">
          <span>Source/category choices unavailable. {choicesError} Applied filters remain unchanged.</span>
          <button type="button" className="btn btn-outline btn-sm" onClick={() => void loadSources()}>Retry catalogue</button>
        </div>}
        {loading && <p role="status" aria-live="polite">Loading stored news...</p>}
        {newsError && <div className="alert alert-error" role="alert">{newsError}</div>}
        {loaded && !items.length && <p role="status">{submittedQuery ? "No news matches this search."
          : Object.keys(applied.filters).length ? "No news matches these filters." : "No stored news yet."}</p>}
        <div className="news-list">
          {items.map((item) => {
            const link = safeHttps(item.url);
            return <article className="card news-card" key={item.id}>
              <div className="news-meta"><span>{item.source} · {item.category}</span>
                <LocalTimestamp value={item.publishedAt} formatter={dateTimeFormatter} now={now} /></div>
              <h2><a href={`/news/${item.id}`} className="link" onClick={(event) => openDetail(event, item.id)}>{item.title}</a></h2><p className="news-summary">{item.summary}</p>
              <div className="news-actions">
                {link ? <a href={link.href} className="link" target="_blank" rel="noopener noreferrer">
                  Open original · {link.hostname}<span className="sr-only"> (opens in a new tab)</span>
                </a> : <span>Original link unavailable</span>}
                <button className="btn btn-outline btn-sm" disabled={busy} data-write
                  onClick={(event) => openPanel(event.currentTarget, item)}
                  aria-label={`Ask about this: ${item.title}`}>Ask about this</button>
              </div>
            </article>;
          })}
        </div>
        {loaded && <section aria-label="Browse continuation" className="browse-continuation">
          <p role="status">{items.length} {submittedQuery ? "bounded search results" : "stored items"} displayed.</p>
          {readAt && <p className="filter-help">Latest page read: <LocalTimestamp value={readAt} formatter={dateTimeFormatter} />. Server read age at response: {readAge.toFixed(1)} seconds. The API may reuse data for up to 60 seconds; live pages are not a fixed snapshot.</p>}
          {appendError && <div role="alert" className="alert alert-error">{appendError}</div>}
          {appending && <p role="status">Loading more stored news...</p>}
          {!submittedQuery && nextCursor && items.length < 200 &&
            <button className="btn btn-outline" disabled={appending} onClick={() => void loadMore()}>{appendError ? "Retry Load more" : "Load more"}</button>}
          {!submittedQuery && items.length >= 200 && nextCursor && <>
            <p>Display limit reached: 200 items. More news may exist.</p>
            <button className="btn btn-outline" onClick={() => void loadNews("", applied)}>Restart browsing</button>
          </>}
          {!submittedQuery && !nextCursor && items.length > 0 && <p>No more pages are currently available.</p>}
        </section>}
      </>}
      </div>
      </section>
      {signedIn && <aside id="agent-panel" className="agent-panel" aria-label="Agent interactions"
        tabIndex={0} hidden={!panelOpen} onKeyDown={trapSheetFocus}>
        <div className="panel-heading"><h2>Ask Newsloom</h2>
          <button className="btn btn-ghost btn-sm" onClick={closePanel}>Close agent panel</button></div>
        {!radar && <BriefingPanel catalog={catalog} active={signedIn && panelOpen} feedback={feedback} />}
        <p className="notice">Research is early access. Quality evaluation is still in progress.</p>
        {selected && <div className="context-chip">
          <span>Current news: {selected.title}</span>
          <button className="btn btn-ghost btn-xs" disabled={busy} aria-label="Remove news context"
            onClick={() => setSelected(null)}>Remove</button>
        </div>}
        {!selected && <p className="context-note">General research · No news item selected</p>}
        <section aria-label="Next research filters">
          <p className="context-note">Browsing filters for the next question</p>
          <FilterChips snapshot={applied} />
        </section>
        {busy && <div aria-live="polite" role="status" className="progress-area">
          <span className="loading loading-spinner loading-sm" aria-hidden="true" />
          {phase ? `${phase.charAt(0).toUpperCase()}${phase.slice(1)}` : "Connecting to the agent"}
          <div className="phase-labels" aria-hidden="true">
            {phases.map((value) => <span key={value} className={value === phase ? "active-phase" : ""}>{value}</span>)}
          </div>
        </div>}
        {(busy || turns.length > 0) && submittedContext && <section aria-label="Submitted research context" className="context-note">
          <p>Context used for this {busy ? "request" : "answer"}</p>
          <p>{submittedContext.item ? `Submitted news: ${submittedContext.item.title}` : "No news item was submitted"}</p>
          <FilterChips snapshot={submittedContext.snapshot} />
        </section>}
        {turns.length > 0 && <ol className="thread" aria-label="Conversation">
          {turns.map((turn, index) => <li key={turn.id} className="turn"
            ref={index === turns.length - 1 ? latestTurn : undefined}>
            <p className="turn-question"><span className="sr-only">You asked: </span>{turn.question}</p>
            <AnswerView answer={turn.answer}
              label={index === turns.length - 1 ? "Research answer" : `Earlier answer ${index + 1}`} />
          </li>)}
        </ol>}
        {!busy && turns.length > 0 && (turns[turns.length - 1]?.followUps.length ?? 0) > 0 &&
          <div className="follow-ups" role="group" aria-label="Suggested follow-ups" data-write>
            {turns[turns.length - 1]?.followUps.map((followUp) => <button key={followUp} type="button"
              className="btn btn-outline btn-xs" onClick={() => void send(followUp)}>{followUp}</button>)}
          </div>}
        {turns.length > 0 && feedback && rated && rated.id === turns[turns.length - 1]?.id &&
          <FeedbackControls client={feedback} label="Rate this answer"
            target={{ type: "research", ref: rated.id }} snapshot={rated.snapshot} />}
        {researchError && <div role="alert" className="alert alert-error">{researchError}</div>}
        {busy && pending && <p className="turn-question pending"><span className="sr-only">You asked: </span>{pending}</p>}
        <form onSubmit={(event) => void ask(event)}>
          <label htmlFor="question" className="composer-label">What would you like to understand?</label>
          <textarea ref={composer} id="question" className="textarea" rows={4} value={question} disabled={busy}
            placeholder="Ask about recent announcements, differences, or trends..."
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); }
            }} aria-describedby="question-help" />
          <div className="composer-footer">
            <p id="question-help">{turns.length ? "Follow-ups use this conversation." : "Stored summaries and metadata only."}</p>
            {busy ? <button type="button" className="btn btn-outline" onClick={() => void stop()}>Stop</button>
              : <button className="btn btn-primary" type="submit" disabled={!question.trim()}>Ask Newsloom</button>}
          </div>
        </form>
        {!busy && turns.length > 0 && <button type="button" className="btn btn-ghost btn-sm new-conversation"
          onClick={newConversation}>New conversation</button>}
      </aside>}
      {authRequired && <div className="alert" role="alert">
        <span>Sign-in is required for {authRequired === "news" ? "news access" : "research"}.</span>
        <button className="btn btn-outline btn-sm" onClick={() => void signIn(authRequired)}>
          Sign in for {authRequired === "news" ? "news" : "research"}</button>
      </div>}
      {error && <div className="alert alert-error error-notice" role="alert">{error}</div>}
      <footer className="page-footer">No web search. Conversations stay in this browser tab. Citations link to the original reporting.</footer>
    </main>
  </>;
}
