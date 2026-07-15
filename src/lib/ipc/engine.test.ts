import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ invoke: vi.fn() }));
vi.mock("@tauri-apps/api/core", () => ({ invoke: mocks.invoke }));

import {
  engineExport,
  engineExportWithOverride,
  engineGetConformance,
  engineGetReadiness,
} from "./engine";

describe("strict export IPC", () => {
  beforeEach(() => mocks.invoke.mockReset());

  it("preserves the legacy export command", async () => {
    mocks.invoke.mockResolvedValueOnce("legacy");
    await expect(engineExport("stl", "/tmp/a.stl")).resolves.toBe("legacy");
    expect(mocks.invoke).toHaveBeenCalledWith("engine_export", {
      format: "stl",
      path: "/tmp/a.stl",
      options: null,
    });
  });

  it("uses the app-only override command", async () => {
    mocks.invoke.mockResolvedValueOnce("approved");
    await expect(engineExportWithOverride("stl", "/tmp/a.stl")).resolves.toBe("approved");
    expect(mocks.invoke).toHaveBeenCalledWith("engine_export_with_override", {
      format: "stl",
      path: "/tmp/a.stl",
      options: null,
    });
  });

  it("reads conformance and readiness through nullable engine calls", async () => {
    mocks.invoke.mockResolvedValueOnce("conformance").mockResolvedValueOnce("readiness");
    await expect(engineGetConformance()).resolves.toBe("conformance");
    await expect(engineGetReadiness()).resolves.toBe("readiness");
    expect(mocks.invoke).toHaveBeenNthCalledWith(1, "engine_get_conformance", undefined);
    expect(mocks.invoke).toHaveBeenNthCalledWith(2, "engine_get_readiness", undefined);
  });
});
