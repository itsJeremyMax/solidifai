import { describe, it, expect } from "vitest";
import { SETTINGS_SECTIONS, SETTINGS_SECTION_IDS } from "./sections";

describe("settings sections registry", () => {
  it("lists the expected sections in order with unique ids", () => {
    expect(SETTINGS_SECTION_IDS).toEqual([
      "viewport",
      "context",
      "manufacturing",
      "workspace",
      "slicers",
      "updates",
      "shortcuts",
      "about",
    ]);
    expect(new Set(SETTINGS_SECTION_IDS).size).toBe(SETTINGS_SECTION_IDS.length);
  });

  it("groups sections under Editor / Workspace / App", () => {
    const groups = [...new Set(SETTINGS_SECTIONS.map((s) => s.group))];
    expect(groups).toEqual(["Editor", "Workspace", "App"]);
  });

  it("every section carries an icon and an element", () => {
    for (const s of SETTINGS_SECTIONS) {
      expect(s.icon).toBeTruthy();
      expect(s.element).toBeTruthy();
      expect(s.label.length).toBeGreaterThan(0);
    }
  });
});
