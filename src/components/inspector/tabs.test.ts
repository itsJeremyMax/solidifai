import { describe, it, expect } from "vitest";
import { INSPECTOR_TABS, isInspectorTab } from "./tabs";

describe("inspector tab registry", () => {
  it("lists the expected tabs in order with unique ids", () => {
    expect(INSPECTOR_TABS.map((t) => t.id)).toEqual([
      "plan",
      "model",
      "requirements",
      "measure",
      "dfm",
      "history",
      "make",
    ]);
    expect(new Set(INSPECTOR_TABS.map((t) => t.id)).size).toBe(INSPECTOR_TABS.length);
  });

  it("validates membership for persisted values", () => {
    expect(isInspectorTab("plan")).toBe(true);
    expect(isInspectorTab("make")).toBe(true);
    expect(isInspectorTab("model")).toBe(true);
    expect(isInspectorTab("nope")).toBe(false);
    expect(isInspectorTab(null)).toBe(false);
    expect(isInspectorTab(42)).toBe(false);
  });
});
