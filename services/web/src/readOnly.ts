import { useSyncExternalStore } from "react";

export const READ_ONLY_HEADER = "x-newsloom-read-only";
const WAKE_UTC_HOUR = 7;

let current: string | null = null;
const listeners = new Set<() => void>();

/** Records whether the news API is serving the overnight snapshot (its time) or live data (null). */
export function reportReadOnly(value: string | null): void {
  const valid = value !== null && !Number.isNaN(Date.parse(value)) ? value : null;
  if (valid === current) return;
  current = valid;
  for (const listener of listeners) listener();
}

export function currentReadOnly(): string | null {
  return current;
}

export function useReadOnly(): string | null {
  return useSyncExternalStore((listener) => {
    listeners.add(listener);
    return () => { listeners.delete(listener); };
  }, () => current);
}

export function readOnlyLine(asOf: string, now = new Date()): string {
  const wake = new Date(now);
  wake.setUTCHours(WAKE_UTC_HOUR, 0, 0, 0);
  if (wake <= now) wake.setUTCDate(wake.getUTCDate() + 1);
  const time = (value: Date) => value.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  return `Read-only until ${time(wake)} · data as of ${time(new Date(asOf))}`;
}
