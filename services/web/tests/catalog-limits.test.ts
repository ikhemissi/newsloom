import { expect, test, vi } from "vitest";
import { McpCatalog } from "../src/catalog";
import { runtimeConfig } from "./fixtures";

test("the 90-second load deadline includes stalled token acquisition", async () => {
  vi.useFakeTimers();
  const setTimer = vi.spyOn(globalThis, "setTimeout");
  const clearTimer = vi.spyOn(globalThis, "clearTimeout");
  try {
    const fetchImpl = vi.fn(async () => new Response("{}"));
    const catalog = new McpCatalog(runtimeConfig, {
      signedIn: () => true, signIn: async () => undefined, signOut: async () => undefined,
      token: () => new Promise<string>(() => undefined),
    }, fetchImpl);
    const result = catalog.recent(new AbortController().signal);
    const deadlineTimer = setTimer.mock.results[
      setTimer.mock.calls.findIndex((call) => call[1] === 90000)
    ];
    expect(setTimer).toHaveBeenCalledWith(expect.any(Function), 90000);
    const assertion = expect(result).rejects.toThrow("timeout");
    await vi.advanceTimersByTimeAsync(89999);
    expect(fetchImpl).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    await assertion;
    expect(fetchImpl).not.toHaveBeenCalled();
    expect(deadlineTimer?.type).toBe("return");
    if (deadlineTimer?.type === "return")
      expect(clearTimer).toHaveBeenCalledWith(deadlineTimer.value);
  } finally {
    setTimer.mockRestore();
    clearTimer.mockRestore();
    vi.useRealTimers();
  }
});
