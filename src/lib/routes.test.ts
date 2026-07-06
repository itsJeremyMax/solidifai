import { describe, it, expect } from "vitest";
import { encodeWsPath, decodeWsPath, editorPath } from "./routes";

describe("routes", () => {
  it("round-trips an absolute workspace path through a single URL segment", () => {
    const p = "/Users/dev/Documents/Solidifai/workspaces/fidget-bracket";
    const enc = encodeWsPath(p);
    expect(enc).not.toContain("/"); // slashes are encoded so it stays one segment
    expect(decodeWsPath(enc)).toBe(p);
  });

  it("builds the editor path", () => {
    expect(editorPath("/a/b")).toBe("/w/" + encodeWsPath("/a/b"));
  });
});
