import { describe, expect, it, vi } from "vitest";

vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn(async (cmd: string) => (cmd === "boom" ? Promise.reject(new Error("x")) : "ok")),
}));

import { engineCall } from "./core";

describe("engineCall", () => {
  it("returns the raw response on success", async () => {
    expect(await engineCall("anything")).toBe("ok");
  });
  it("returns null when the engine call rejects (engine not ready)", async () => {
    expect(await engineCall("boom")).toBeNull();
  });
});
