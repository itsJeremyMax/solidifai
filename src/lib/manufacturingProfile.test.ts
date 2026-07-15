import { describe, it, expect, vi } from "vitest";
vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));
import { invoke } from "@tauri-apps/api/core";
import { getWorkspaceProfile, setWorkspaceProfile, processSettings } from "./manufacturingProfile";

describe("manufacturingProfile ipc", () => {
  it("set forwards set + unset", async () => {
    vi.mocked(invoke).mockResolvedValue({
      resolved: {},
      overrides: {},
      material: { id: "pla", label: "PLA" },
    });
    await setWorkspaceProfile({ design: { wallMm: 1.6 } }, ["process.infillPct"]);
    expect(invoke).toHaveBeenCalledWith("set_workspace_manufacturing_profile", {
      set: { design: { wallMm: 1.6 } },
      unset: ["process.infillPct"],
    });
  });
  it("get returns the view shape", async () => {
    vi.mocked(invoke).mockResolvedValue({
      resolved: { design: { wallMm: 2.4 } },
      overrides: {},
      material: { id: "pla", label: "PLA" },
    });
    const v = await getWorkspaceProfile();
    expect(v.resolved.design.wallMm).toBe(2.4);
  });
  it("exposes process-specific settings only for FDM", () => {
    expect(processSettings({ id: "cnc", settings: { overhangDeg: 45 } })).toEqual({});
    expect(processSettings({ id: "cnc", settings: { nozzleMm: 0.4 } })).toEqual({});
  });
});
