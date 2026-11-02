import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

if (typeof window !== "undefined") window.scrollTo = vi.fn();
afterEach(() => {
  cleanup();
  if (typeof window !== "undefined") window.history.replaceState(null, "", "/");
});
