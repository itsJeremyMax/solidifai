import { describe, it, expect } from "vitest";
import { deepLinkToRoute } from "./deepLink";
import { editorPath } from "./routes";

describe("deepLinkToRoute", () => {
  it("maps known actions to routes", () => {
    expect(deepLinkToRoute("solidifai://settings")).toBe("/settings");
    expect(deepLinkToRoute("solidifai://materials")).toBe("/materials");
    expect(deepLinkToRoute("solidifai://factory")).toBe("/factory");
  });

  it("maps a workspace link to the editor route", () => {
    const p = "/Users/x/ws/fidget";
    expect(deepLinkToRoute("solidifai://workspace?path=" + encodeURIComponent(p))).toBe(
      editorPath(p),
    );
  });

  it("falls back to home on a workspace link with no path", () => {
    expect(deepLinkToRoute("solidifai://workspace")).toBe("/");
  });

  it("falls back to home on unknown or unparseable input", () => {
    expect(deepLinkToRoute("solidifai://nope")).toBe("/");
    expect(deepLinkToRoute("garbage")).toBe("/");
  });
});
