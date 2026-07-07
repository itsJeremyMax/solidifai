import { describe, it, expect } from "vitest";
import { nextActionFor, shouldRunPeriodicCheck, updateSurface } from "./useUpdater";

describe("nextActionFor", () => {
  it("notify => show indicator, no auto download", () => {
    expect(nextActionFor("notify", true)).toBe("show-indicator");
  });
  it("autoDownload => download immediately", () => {
    expect(nextActionFor("autoDownload", true)).toBe("download");
  });
  it("silent => download then defer restart", () => {
    expect(nextActionFor("silent", true)).toBe("download-silent");
  });
  it("no update => idle regardless of behavior", () => {
    expect(nextActionFor("notify", false)).toBe("idle");
    expect(nextActionFor("silent", false)).toBe("idle");
  });
});

describe("updateSurface", () => {
  it("shows nothing while idle or checking", () => {
    expect(updateSurface("idle", false, false)).toBe("none");
    expect(updateSurface("checking", false, false)).toBe("none");
  });

  it("shows nothing on the Updates page (the page is its own surface)", () => {
    expect(updateSurface("available", false, true)).toBe("none");
    expect(updateSurface("downloading", true, true)).toBe("none");
    expect(updateSurface("ready", true, true)).toBe("none");
  });

  it("announces a live, not-yet-folded update as the companion", () => {
    expect(updateSurface("available", false, false)).toBe("companion");
    expect(updateSurface("downloading", false, false)).toBe("companion");
    expect(updateSurface("ready", false, false)).toBe("companion");
    expect(updateSurface("error", false, false)).toBe("companion");
  });

  it("hands off to the header pill once the companion is folded/dismissed", () => {
    expect(updateSurface("available", true, false)).toBe("pill");
    expect(updateSurface("downloading", true, false)).toBe("pill");
    expect(updateSurface("ready", true, false)).toBe("pill");
    expect(updateSurface("error", true, false)).toBe("pill");
  });

  it("never returns both: the pill and companion are mutually exclusive", () => {
    // For every state, at most one CTA surface is chosen.
    for (const status of ["available", "downloading", "ready", "error"] as const) {
      for (const dismissed of [true, false]) {
        for (const onPage of [true, false]) {
          const s = updateSurface(status, dismissed, onPage);
          expect(["none", "pill", "companion"]).toContain(s);
        }
      }
    }
  });
});

describe("shouldRunPeriodicCheck", () => {
  const HOUR = 60 * 60 * 1000;
  it("runs when nothing has been checked yet", () => {
    expect(shouldRunPeriodicCheck(null, 1_000, 6 * HOUR)).toBe(true);
  });
  it("skips while inside the interval", () => {
    const now = 10 * HOUR;
    expect(shouldRunPeriodicCheck(now - HOUR, now, 6 * HOUR)).toBe(false);
  });
  it("runs once the interval has fully elapsed", () => {
    const now = 10 * HOUR;
    expect(shouldRunPeriodicCheck(now - 6 * HOUR, now, 6 * HOUR)).toBe(true);
  });
  it("treats exactly-at-interval as due", () => {
    expect(shouldRunPeriodicCheck(0, 6 * HOUR, 6 * HOUR)).toBe(true);
  });
});
