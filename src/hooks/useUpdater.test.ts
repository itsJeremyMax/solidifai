import { describe, it, expect } from "vitest";
import { nextActionFor, shouldRunPeriodicCheck } from "./useUpdater";

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
