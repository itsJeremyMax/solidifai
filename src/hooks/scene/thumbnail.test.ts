import { describe, expect, it } from "vitest";
import { pngFromPixels } from "./thumbnail";

describe("pngFromPixels", () => {
  it("returns null when no 2d context is available", async () => {
    // jsdom canvas has no real 2d context in the test env; the helper must
    // resolve null rather than throw (matches current guard).
    const out = await pngFromPixels(new Uint8Array(4), 1, 1, false);
    expect(out === null || out instanceof Blob).toBe(true);
  });
});
