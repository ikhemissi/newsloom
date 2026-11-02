// @vitest-environment node
import { afterEach, expect, test } from "vitest";
import { localDateTimeFormat } from "../src/timestamps";

const originalTimezone = process.env.TZ;
afterEach(() => {
  if (originalTimezone === undefined) delete process.env.TZ;
  else process.env.TZ = originalTimezone;
});

test.each([
  ["Europe/Paris", "03", 1, "00", "+1"],
  ["America/New_York", "02", 19, "00", "-5"],
  ["Asia/Kathmandu", "03", 5, "45", "+5:45"],
  ["UTC", "03", 0, "00", ""],
] as const)("browser default timezone %s converts midnight once with an explicit offset", (zone, day, hour, minute, offset) => {
  process.env.TZ = zone;
  const formatter = localDateTimeFormat();
  const parts = Object.fromEntries(formatter.formatToParts(new Date("2026-11-03T00:00:00Z"))
    .map((part) => [part.type, part.value]));
  expect(parts.year).toBe("2026");
  expect(parts.month).toBe("11");
  expect(parts.day).toBe(day);
  expect(Number(parts.hour)).toBe(formatter.resolvedOptions().hour12 ? hour % 12 || 12 : hour);
  expect(parts.minute).toBe(minute);
  expect(parts.second).toBe("00");
  const actualOffset = parts.timeZoneName?.replace(/GMT|UTC/g, "").replace("\u2212", "-");
  expect(actualOffset === "+0" ? "" : actualOffset).toBe(offset);
});

test("offsets follow each instant's DST rules and new formatters follow zone changes", () => {
  process.env.TZ = "America/New_York";
  const formatter = localDateTimeFormat();
  const before = formatter.formatToParts(new Date("2026-11-01T05:30:00Z"));
  const after = formatter.formatToParts(new Date("2026-11-01T06:30:00Z"));
  expect(before.find((part) => part.type === "hour")?.value).toBe(after.find((part) => part.type === "hour")?.value);
  expect(before.find((part) => part.type === "timeZoneName")?.value).toContain("-4");
  expect(after.find((part) => part.type === "timeZoneName")?.value).toContain("-5");
  process.env.TZ = "Europe/Paris";
  expect(localDateTimeFormat().formatToParts(new Date("2026-07-01T00:00:00Z"))
    .find((part) => part.type === "timeZoneName")?.value).toContain("+2");
});
