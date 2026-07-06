// @vitest-environment jsdom
import { describe, it, expect, beforeEach, vi } from "vitest";
import { readLastRoute, saveLastRoute } from "./lastRoute";

// Node's experimental global localStorage shadows jsdom's and lacks methods here;
// install a simple in-memory one.
const store = new Map<string, string>();
beforeEach(() => {
  store.clear();
  vi.stubGlobal("localStorage", {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => {
      store.set(k, v);
    },
    removeItem: (k: string) => {
      store.delete(k);
    },
    clear: () => store.clear(),
  });
});

describe("lastRoute", () => {
  it("round-trips a saved route", () => {
    saveLastRoute("/settings/about");
    expect(readLastRoute()).toBe("/settings/about");
  });

  it("returns null when nothing is saved", () => {
    expect(readLastRoute()).toBeNull();
  });
});
