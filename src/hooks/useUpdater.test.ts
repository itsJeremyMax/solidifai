import { describe, it, expect } from "vitest";
import { nextActionFor } from "./useUpdater";

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
