import { afterEach, expect, test } from "vitest";
import { UiFailure } from "../src/domain";
import { currentReadOnly, readOnlyLine, reportReadOnly } from "../src/readOnly";
import { guardedFetch } from "../src/research";

const endpoint = "https://api.test/api/v1/radar";
const asOf = "2026-11-10T22:45:00+00:00";
const respond = (status: number, readOnly?: string) => async () => new Response(JSON.stringify({}), {
  status, headers: readOnly ? { "X-Newsloom-Read-Only": readOnly } : {},
});

afterEach(() => reportReadOnly(null));

test("API responses switch the read-only state on and off", async () => {
  await guardedFetch(endpoint, "token", new AbortController().signal, respond(200, asOf), [], true)(endpoint);
  expect(currentReadOnly()).toBe(asOf);
  await guardedFetch(endpoint, "token", new AbortController().signal, respond(200), [], true)(endpoint);
  expect(currentReadOnly()).toBeNull();
});

test("a read-only refusal is its own failure, and unobserved clients are unaffected", async () => {
  await expect(guardedFetch(endpoint, "token", new AbortController().signal, respond(503, asOf), [], true)(endpoint))
    .rejects.toEqual(new UiFailure("read_only"));
  expect(currentReadOnly()).toBe(asOf);
  await expect(guardedFetch(endpoint, "token", new AbortController().signal, respond(503))(endpoint))
    .rejects.toEqual(new UiFailure("unavailable"));
  await guardedFetch(endpoint, null, new AbortController().signal, respond(200))(endpoint);
  expect(currentReadOnly()).toBe(asOf);
});

test("invalid header values are ignored and the line names the next 07:00 UTC wake", () => {
  reportReadOnly("not a time");
  expect(currentReadOnly()).toBeNull();
  const time = (value: string) => new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  expect(readOnlyLine(asOf, new Date("2026-11-10T23:30:00Z")))
    .toBe(`Read-only until ${time("2026-11-11T07:00:00Z")} · data as of ${time(asOf)}`);
  expect(readOnlyLine(asOf, new Date("2026-11-11T03:00:00Z")))
    .toBe(`Read-only until ${time("2026-11-11T07:00:00Z")} · data as of ${time(asOf)}`);
});
