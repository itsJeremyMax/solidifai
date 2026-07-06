import { describe, it, expect } from "vitest";
import { shouldShowWhatsNew } from "./useWhatsNew";

describe("shouldShowWhatsNew", () => {
  it("hidden on first ever launch (no lastSeen)", () => {
    expect(shouldShowWhatsNew(null, "0.3.0")).toBe(false);
  });
  it("shown when updated", () => {
    expect(shouldShowWhatsNew("0.2.0", "0.3.0")).toBe(true);
  });
  it("hidden when unchanged", () => {
    expect(shouldShowWhatsNew("0.3.0", "0.3.0")).toBe(false);
  });
  it("shown across consecutive beta builds (prerelease not coerced away)", () => {
    expect(shouldShowWhatsNew("0.3.0-beta.1", "0.3.0-beta.2")).toBe(true);
    expect(shouldShowWhatsNew("0.3.0-beta.2", "0.3.0-beta.2")).toBe(false);
    expect(shouldShowWhatsNew("0.3.0-beta.2", "0.3.0")).toBe(true);
  });
});
