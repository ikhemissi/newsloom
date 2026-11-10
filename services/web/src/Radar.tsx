import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { failureMessage } from "./domain";
import { safeHttps } from "./config";
import type { CardState, ProductDetail, Radar, RadarCard, RadarClient, RadarEntry, StackEntry, Tier } from "./radar";
import { daysUntil, entryCards, statusLabels, tierLabels } from "./radar";

const shortDate = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", timeZone: "UTC" });
const fromDay = (day: string) => shortDate.format(new Date(`${day}T00:00:00Z`));
const fromTime = (value: string) => shortDate.format(new Date(value));
const WORTH_SHOWN = 8;
const GROUP_SHOWN = 4;

type Navigate = (path: string, event?: React.MouseEvent<HTMLAnchorElement>) => void;
type Ask = (card: RadarCard, opener: HTMLButtonElement) => void;

function useLoad<T>(load: (signal: AbortSignal) => Promise<T>, deps: unknown[]) {
  const [value, setValue] = useState<T | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  const [version, setVersion] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setError("");
    load(controller.signal).then((result) => {
      if (!controller.signal.aborted) { setValue(result); setLoaded(true); }
    }, (failure) => { if (!controller.signal.aborted) setError(failureMessage(failure)); });
    return () => controller.abort();
  }, [...deps, version]);
  return { value, loaded, error, reload: () => setVersion((current) => current + 1) };
}

function label(card: RadarCard, now: Date): string {
  if (card.articleKind === "security") return "Security";
  if (card.deadline && ["retired", "deprecated"].includes(card.status)) {
    const days = daysUntil(card.deadline, now);
    return `Retires ${fromDay(card.deadline)}${days >= 0 ? ` · in ${days} days` : ""}`;
  }
  if (card.articleKind === "regulation") return "Regulation";
  return statusLabels[card.status] ?? "";
}

function vendors(cards: RadarCard[]): string[] {
  return [...new Set(cards.flatMap((card) => card.products.map((product) => product.vendor)))];
}

function Products({ card, navigate }: { card: RadarCard; navigate: Navigate }) {
  return <span className="radar-products">{card.products.map((product, index) => <span key={product.id}>
    {index > 0 && " · "}
    <a href={`/products/${product.id}`} className="link" onClick={(event) => navigate(`/products/${product.id}`, event)}>{product.name}</a>
  </span>)}</span>;
}

function Actions({ cards, onState, onFollow, onAsk, navigate }: {
  cards: RadarCard[]; onState: (cards: RadarCard[], state: CardState | null) => void;
  onFollow: (cards: RadarCard[]) => void; onAsk: Ask; navigate: Navigate;
}) {
  const first = cards[0];
  if (!first) return null;
  const subject = cards.length > 1 ? `${cards.length} updates on ${first.capability}` : first.statement;
  return <div className="radar-actions">
    {cards.length === 1 && <Products card={first} navigate={navigate} />}
    <span className="radar-buttons" data-write>
      <button className="btn btn-ghost btn-xs" aria-label={`Done: ${subject}`} onClick={() => onState(cards, "done")}>✓ Done</button>
      <button className="btn btn-ghost btn-xs" aria-label={`Snooze for 7 days: ${subject}`} onClick={() => onState(cards, "snoozed")}>◷ Snooze</button>
      <button className="btn btn-ghost btn-xs" aria-label={`Follow products: ${subject}`} onClick={() => onFollow(cards)}>☆ Follow</button>
      <button className="btn btn-outline btn-xs" aria-label={`Ask about this: ${subject}`}
        onClick={(event) => onAsk(first, event.currentTarget)}>Ask</button>
    </span>
  </div>;
}

function Entry({ entry, tier, now, ...handlers }: {
  entry: RadarEntry; tier: Tier; now: Date; navigate: Navigate; onAsk: Ask;
  onState: (cards: RadarCard[], state: CardState | null) => void; onFollow: (cards: RadarCard[]) => void;
}) {
  const cards = entryCards(entry);
  const [all, setAll] = useState(false);
  if (entry.kind === "group") return <article className={`card radar-card ${tier}`} aria-label={`${entry.capability}, ${cards.length} updates`}>
    <div className="radar-meta"><strong className="radar-capability">{entry.capability}</strong>
      <span>{vendors(cards).length} vendors</span></div>
    <ul className="radar-group">{(all ? cards : cards.slice(0, GROUP_SHOWN)).map((card) => {
      const link = safeHttps(card.url);
      return <li key={card.id}>
        <span className="radar-label">{label(card, now)}</span>
        <span className="radar-vendor">{vendors([card]).join(", ")}</span>
        {link ? <a href={link.href} className="link" target="_blank" rel="noopener noreferrer">{card.statement}</a>
          : <span>{card.statement}</span>}
        <span className="radar-date">{fromTime(card.publishedAt)}</span>
      </li>;
    })}</ul>
    {cards.length > GROUP_SHOWN && <button className="btn btn-ghost btn-xs radar-more" aria-expanded={all}
      onClick={() => setAll(!all)}>{all ? "Show fewer" : `Show all ${cards.length}`}</button>}
    <Actions cards={cards} {...handlers} />
  </article>;
  const card = entry.card;
  const link = safeHttps(card.url);
  return <article className={`card radar-card ${tier}`} aria-label={card.statement}>
    <div className="radar-meta">
      <span>{[label(card, now), vendors([card]).join(", ")].filter(Boolean).join(" · ")}</span>
      <span className="radar-date">{fromTime(card.publishedAt)}</span>
    </div>
    <p className="radar-statement">{link ? <a href={link.href} className="link" target="_blank" rel="noopener noreferrer">
      {card.statement}<span className="sr-only"> (opens the source in a new tab)</span></a> : card.statement}</p>
    {card.reason && tier !== "later" && <p className="radar-reason">Why: {card.reason}</p>}
    <Actions cards={[card]} {...handlers} />
  </article>;
}

export function RadarPage({ client, briefing, onAsk, navigate, now = new Date() }: {
  client: RadarClient; briefing: ReactNode; onAsk: Ask; navigate: Navigate; now?: Date;
}) {
  const [window, setWindow] = useState<7 | 30>(7);
  const [moreWorth, setMoreWorth] = useState(false);
  const [showHidden, setShowHidden] = useState(false);
  const [status, setStatus] = useState("");
  const heading = useRef<HTMLHeadingElement>(null);
  const { value: radar, error, reload } = useLoad((signal) => client.radar(window, signal), [client, window]);
  async function update(work: (signal: AbortSignal) => Promise<unknown>, message: string) {
    try { await work(new AbortController().signal); setStatus(message); reload(); }
    catch (failure) { setStatus(failureMessage(failure)); }
  }
  const onState = (cards: RadarCard[], state: CardState | null) => void update(
    (signal) => Promise.all(cards.map((card) => client.setCard(card.id, state, signal))),
    state === "done" ? "Marked done." : state === "snoozed" ? "Snoozed for 7 days." : "Restored.");
  const onFollow = (cards: RadarCard[]) => void update(async (signal) => {
    const current = await client.stack(signal);
    const ids = new Set(current.map((entry) => entry.id));
    cards.forEach((card) => card.products.forEach((product) => ids.add(product.id)));
    await client.setStack([...ids], signal);
  }, "Added to My stack.");
  const handlers = { now, navigate, onAsk, onState, onFollow };
  return <section aria-label="Radar" className="radar">
    <div className="radar-top">
      <h1 ref={heading} tabIndex={-1} className="radar-day">Today · {new Intl.DateTimeFormat(undefined, { weekday: "short", day: "numeric", month: "short" }).format(now)}</h1>
      <label className="radar-window"><span className="sr-only">Time window</span>
        <select className="select select-sm" value={window} onChange={(event) => setWindow(event.target.value === "30" ? 30 : 7)}>
          <option value="7">7 days</option><option value="30">30 days</option>
        </select></label>
      {radar && radar.hidden.length > 0 && <button className="btn btn-ghost btn-sm" aria-expanded={showHidden}
        onClick={() => setShowHidden(!showHidden)}>Hidden ({radar.hidden.length})</button>}
    </div>
    {briefing}
    <p role="status" className="sr-only">{status}</p>
    {error && <div role="alert" className="alert alert-error"><span>{error}</span>
      <button className="btn btn-outline btn-sm" onClick={reload}>Retry</button></div>}
    {!radar && !error && <p role="status">Loading your radar…</p>}
    {radar && <Content radar={radar} handlers={handlers} moreWorth={moreWorth} setMoreWorth={setMoreWorth}
      showHidden={showHidden} />}
  </section>;
}

function Content({ radar, handlers, moreWorth, setMoreWorth, showHidden }: {
  radar: Radar; moreWorth: boolean; setMoreWorth: (value: boolean) => void; showHidden: boolean;
  handlers: { now: Date; navigate: Navigate; onAsk: Ask;
    onState: (cards: RadarCard[], state: CardState | null) => void; onFollow: (cards: RadarCard[]) => void };
}) {
  const worth = radar.tiers.worth_knowing;
  return <>
    {showHidden && <section aria-label="Hidden" className="radar-hidden">
      <h2>Hidden</h2>
      <ul>{radar.hidden.map((card) => <li key={card.id}>
        <span>{card.state === "snoozed" ? "Snoozed" : "Done"} · {card.statement}</span>
        <button className="btn btn-ghost btn-xs" data-write aria-label={`Restore: ${card.statement}`}
          onClick={() => handlers.onState([card], null)}>Restore</button>
      </li>)}</ul>
    </section>}
    {radar.deadlines.length > 0 && <section aria-label="Deadlines" className="radar-deadlines">
      <h2 className="sr-only">Deadlines</h2>
      <ul>{radar.deadlines.slice(0, 6).map((card) => {
        const link = safeHttps(card.url);
        return <li key={card.id}><strong>{card.deadline && fromDay(card.deadline)}</strong>{" "}
          {link ? <a href={link.href} className="link" target="_blank" rel="noopener noreferrer">{card.statement}</a> : card.statement}</li>;
      })}</ul>
    </section>}
    <section aria-labelledby="tier-act_now" className="radar-tier">
      <h2 id="tier-act_now" className="tier-heading act_now">{tierLabels.act_now} · {radar.tiers.act_now.length}</h2>
      {radar.tiers.act_now.length === 0 && <p>Nothing needs action right now.</p>}
      {radar.tiers.act_now.map((entry) => <Entry key={entryCards(entry)[0]?.id} entry={entry} tier="act_now" {...handlers} />)}
    </section>
    <section aria-labelledby="tier-worth_knowing" className="radar-tier">
      <h2 id="tier-worth_knowing" className="tier-heading">{tierLabels.worth_knowing} · {worth.length}</h2>
      {(moreWorth ? worth : worth.slice(0, WORTH_SHOWN)).map((entry) =>
        <Entry key={entryCards(entry)[0]?.id} entry={entry} tier="worth_knowing" {...handlers} />)}
      {worth.length > WORTH_SHOWN && <button className="btn btn-ghost btn-sm" onClick={() => setMoreWorth(!moreWorth)}>
        {moreWorth ? "Show fewer" : `Show ${worth.length - WORTH_SHOWN} more`}</button>}
    </section>
    <details className="radar-tier radar-later">
      <summary><h2 className="tier-heading">{tierLabels.later} · {radar.tiers.later.length}</h2></summary>
      {radar.tiers.later.map((entry) => <Entry key={entryCards(entry)[0]?.id} entry={entry} tier="later" {...handlers} />)}
    </details>
  </>;
}

export function ProductPage({ client, id, navigate, onBack }: {
  client: RadarClient; id: string; navigate: Navigate; onBack: () => void;
}) {
  const product = useLoad((signal) => client.product(id, signal), [client, id]);
  const stack = useLoad((signal) => client.stack(signal), [client]);
  const following = !!stack.value?.some((entry) => entry.id === id);
  async function toggle(detail: ProductDetail) {
    const current = stack.value ?? [];
    const ids = following ? current.filter((entry) => entry.id !== id).map((entry) => entry.id)
      : [...current.map((entry) => entry.id), detail.id];
    try { await client.setStack(ids, new AbortController().signal); stack.reload(); } catch { stack.reload(); }
  }
  const detail = product.value;
  return <section aria-label="Product" className="radar-product">
    <button className="btn btn-outline btn-sm" onClick={onBack}>Back</button>
    {product.error && <div role="alert" className="alert alert-error">{product.error}</div>}
    {!detail && !product.error && <p role="status">{product.loaded ? "Product not found." : "Loading product…"}</p>}
    {detail && <>
      <div className="radar-product-head"><h1>{detail.name}</h1>
        <button className="btn btn-outline btn-sm" data-write aria-pressed={following} onClick={() => void toggle(detail)}>
          {following ? "★ Following" : "☆ Follow"}</button></div>
      <p>{detail.vendor}{detail.related.map((related) => <span key={related.id}> · {related.relation === "part_of" ? "part of" : "replaces"}{" "}
        <a href={`/products/${related.id}`} className="link" onClick={(event) => navigate(`/products/${related.id}`, event)}>{related.name}</a></span>)}</p>
      {detail.aliases.length > 0 && <p className="radar-aliases">Also known as: {detail.aliases.join(", ")}</p>}
      <h2>Timeline</h2>
      <ol className="radar-timeline">{detail.timeline.map((card) => {
        const link = safeHttps(card.url);
        return <li key={card.id}>
          <span className="radar-date">{fromTime(card.publishedAt)}</span>
          <span className="radar-label">{statusLabels[card.status] ?? "—"}</span>
          {link ? <a href={link.href} className="link" target="_blank" rel="noopener noreferrer">{card.statement}</a> : <span>{card.statement}</span>}
          <span className="radar-source">{card.source}</span>
        </li>;
      })}</ol>
    </>}
  </section>;
}

export function StackPage({ client, navigate }: { client: RadarClient; navigate: Navigate }) {
  const stack = useLoad((signal) => client.stack(signal), [client]);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<StackEntry[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    if (query.trim().length < 2) { setResults([]); return; }
    const timer = setTimeout(() => {
      client.search(query.trim(), controller.signal).then(setResults, (failure) => setError(failureMessage(failure)));
    }, 200);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [client, query]);
  async function save(ids: string[]) {
    try { await client.setStack(ids, new AbortController().signal); setError(""); stack.reload(); }
    catch (failure) { setError(failureMessage(failure)); }
  }
  const current = stack.value ?? [];
  const chosen = new Set(current.map((entry) => entry.id));
  const name = (entry: StackEntry) => entry.kind === "product" && entry.vendor ? `${entry.name} (${entry.vendor})` : entry.name;
  return <section aria-label="My stack" className="radar-stack">
    <h1>My stack</h1>
    <label className="radar-stack-search" data-write><span className="sr-only">Add a vendor or product</span>
      <input className="input" type="search" placeholder="Add a vendor or product…" value={query}
        onChange={(event) => setQuery(event.target.value)} /></label>
    {results.length > 0 && <ul className="radar-results" data-write aria-label="Matches">{results.filter((entry) => !chosen.has(entry.id)).map((entry) =>
      <li key={entry.id}><button className="btn btn-ghost btn-sm" onClick={() => { setQuery(""); void save([...chosen, entry.id]); }}>
        + {name(entry)}</button></li>)}</ul>}
    {(error || stack.error) && <div role="alert" className="alert alert-error">{error || stack.error}</div>}
    <ul className="radar-chips" aria-label="Followed">{current.map((entry) => <li key={entry.id} className="badge badge-outline badge-lg">
      {entry.kind === "product" ? <a href={`/products/${entry.id}`} className="link"
        onClick={(event) => navigate(`/products/${entry.id}`, event)}>{name(entry)}</a> : name(entry)}
      <button className="btn btn-ghost btn-xs" data-write aria-label={`Remove ${entry.name}`}
        onClick={() => void save(current.filter((other) => other.id !== entry.id).map((other) => other.id))}>✕</button>
    </li>)}</ul>
  </section>;
}
