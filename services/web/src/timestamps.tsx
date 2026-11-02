import { useEffect, useState } from "react";

export function localDateTimeFormat(): Intl.DateTimeFormat {
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit", timeZoneName: "shortOffset",
  });
}

export function useDisplayClock(active: boolean): number {
  const [clock, setClock] = useState(() => ({ now: Date.now() }));
  useEffect(() => {
    if (!active) return;
    // Refresh formatting even when only the timezone, not the clock, changes.
    const update = () => setClock({ now: Date.now() });
    const visible = () => { if (document.visibilityState === "visible") update(); };
    update();
    const timer = window.setInterval(update, 60_000);
    window.addEventListener("focus", update);
    document.addEventListener("visibilitychange", visible);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", update);
      document.removeEventListener("visibilitychange", visible);
    };
  }, [active]);
  return clock.now;
}

export function LocalTimestamp({ value, formatter, now }: {
  value: string; formatter: Intl.DateTimeFormat; now?: number;
}) {
  return <span className="local-timestamp">
    <time dateTime={value}>{formatter.format(new Date(value))}</time>
    {now !== undefined && Date.parse(value) > now && <span className="badge badge-outline badge-sm future-date">
      Future-dated<span className="sr-only"> (later than the current time on your device)</span>
    </span>}
  </span>;
}
