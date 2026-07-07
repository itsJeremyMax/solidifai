import { describe, it, expect } from "vitest";
import {
  APP_SETTINGS_SECTIONS,
  APP_SETTINGS_SECTION_IDS,
  WORKSPACE_SETTINGS_SECTIONS,
  WORKSPACE_SETTINGS_SECTION_IDS,
  type SettingsSection,
} from "./sections";

const wellFormed = (sections: SettingsSection[]) => {
  for (const s of sections) {
    expect(s.icon).toBeTruthy();
    expect(s.element).toBeTruthy();
    expect(s.label.length).toBeGreaterThan(0);
  }
};

describe("settings section registries", () => {
  it("app settings lists the app-scoped sections in order with unique ids", () => {
    expect(APP_SETTINGS_SECTION_IDS).toEqual([
      "viewport",
      "instructions",
      "manufacturing",
      "slicers",
      "updates",
      "shortcuts",
      "about",
    ]);
    expect(new Set(APP_SETTINGS_SECTION_IDS).size).toBe(APP_SETTINGS_SECTION_IDS.length);
  });

  it("workspace settings lists the workspace-scoped sections in order with unique ids", () => {
    expect(WORKSPACE_SETTINGS_SECTION_IDS).toEqual([
      "instructions",
      "skills",
      "manufacturing",
      "workspace",
    ]);
    expect(new Set(WORKSPACE_SETTINGS_SECTION_IDS).size).toBe(
      WORKSPACE_SETTINGS_SECTION_IDS.length,
    );
  });

  it("app settings groups under Editor / Defaults / App", () => {
    const groups = [...new Set(APP_SETTINGS_SECTIONS.map((s) => s.group))];
    expect(groups).toEqual(["Editor", "Defaults", "App"]);
  });

  it("workspace settings is a single group (renders as a flat list)", () => {
    const groups = [...new Set(WORKSPACE_SETTINGS_SECTIONS.map((s) => s.group))];
    expect(groups).toEqual(["Workspace"]);
  });

  it("every section carries an icon, an element, and a label", () => {
    wellFormed(APP_SETTINGS_SECTIONS);
    wellFormed(WORKSPACE_SETTINGS_SECTIONS);
  });
});
