import { describe, it, expect } from "vitest";
import { INSPECTOR_TABS, isInspectorTab } from "./tabs";

describe("inspector tab registry", () => {
  it("lists the expected tabs in order with unique ids", () => {
    expect(INSPECTOR_TABS.map((t) => t.id)).toEqual(["model", "checks", "activity", "make"]);
    expect(new Set(INSPECTOR_TABS.map((t) => t.id)).size).toBe(INSPECTOR_TABS.length);
  });

  it("validates membership for persisted values", () => {
    expect(isInspectorTab("model")).toBe(true);
    expect(isInspectorTab("checks")).toBe(true);
    expect(isInspectorTab("activity")).toBe(true);
    expect(isInspectorTab("make")).toBe(true);
    // Stale pre-consolidation ids fall back to the default tab via the guard.
    expect(isInspectorTab("plan")).toBe(false);
    expect(isInspectorTab("dfm")).toBe(false);
    expect(isInspectorTab("nope")).toBe(false);
    expect(isInspectorTab(null)).toBe(false);
    expect(isInspectorTab(42)).toBe(false);
  });
});
