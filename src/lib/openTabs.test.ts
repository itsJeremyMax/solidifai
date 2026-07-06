// @vitest-environment jsdom
import { describe, it, expect, beforeEach, vi } from "vitest";
import { readOpenTabs, saveOpenTabs } from "./openTabs";

// Node's experimental global localStorage shadows jsdom's and lacks methods here;
// install a simple in-memory one (mirrors lastRoute.test.ts).
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

describe("openTabs", () => {
  it("round-trips open + focused", () => {
    saveOpenTabs({ open: ["/ws/a", "/ws/b"], focused: "/ws/b" });
    expect(readOpenTabs()).toEqual({ open: ["/ws/a", "/ws/b"], focused: "/ws/b" });
  });

  it("round-trips with null focused", () => {
    saveOpenTabs({ open: ["/ws/a"], focused: null });
    expect(readOpenTabs()).toEqual({ open: ["/ws/a"], focused: null });
  });

  it("round-trips an empty open set", () => {
    saveOpenTabs({ open: [], focused: null });
    expect(readOpenTabs()).toEqual({ open: [], focused: null });
  });

  it("returns null when nothing is saved", () => {
    expect(readOpenTabs()).toBeNull();
  });

  it("returns null on garbage JSON", () => {
    store.set("solidifai.openTabs", "not-json{{{");
    expect(readOpenTabs()).toBeNull();
  });

  it("returns null when the stored value is missing the open array", () => {
    store.set("solidifai.openTabs", JSON.stringify({ focused: "/ws/a" }));
    expect(readOpenTabs()).toBeNull();
  });

  it("filters non-string entries from the open array", () => {
    store.set("solidifai.openTabs", JSON.stringify({ open: ["/ws/a", 42, null], focused: null }));
    expect(readOpenTabs()).toEqual({ open: ["/ws/a"], focused: null });
  });
});
