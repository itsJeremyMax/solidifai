// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act, waitFor, cleanup } from "@testing-library/react";
vi.mock("../lib/manufacturingProfile");
import * as ipc from "../lib/manufacturingProfile";
import { useManufacturingProfile } from "./useManufacturingProfile";
import type { ProfileValues } from "../lib/manufacturingProfile";

const view = (resolved: ProfileValues, overrides: ProfileValues = {}) => ({
  resolved,
  overrides,
  material: { id: "pla", label: "PLA" },
});

describe("useManufacturingProfile", () => {
  beforeEach(() => {
    vi.mocked(ipc.getWorkspaceProfile).mockResolvedValue(view({ design: { wallMm: 2.4 } }));
  });
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("loads then commits a field, adopting backend truth", async () => {
    vi.mocked(ipc.setWorkspaceProfile).mockResolvedValue(
      view({ design: { wallMm: 1.6 } }, { design: { wallMm: 1.6 } }),
    );
    const { result } = renderHook(() => useManufacturingProfile("workspace"));
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => {
      await result.current.setField("design", "wallMm", 1.6);
    });
    expect(ipc.setWorkspaceProfile).toHaveBeenCalledWith({ design: { wallMm: 1.6 } }, []);
    expect(result.current.view.resolved.design.wallMm).toBe(1.6);
  });

  it("reset issues an unset", async () => {
    vi.mocked(ipc.setWorkspaceProfile).mockResolvedValue(view({ design: { wallMm: 2.4 } }));
    const { result } = renderHook(() => useManufacturingProfile("workspace"));
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => {
      await result.current.resetField("design", "wallMm");
    });
    expect(ipc.setWorkspaceProfile).toHaveBeenCalledWith({}, ["design.wallMm"]);
  });

  it("reverts to prior view and surfaces error when write fails", async () => {
    vi.mocked(ipc.setWorkspaceProfile).mockRejectedValue(new Error("disk full"));
    const { result } = renderHook(() => useManufacturingProfile("workspace"));
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => {
      await result.current.setField("design", "wallMm", 1.6);
    });
    // View reverts to the originally loaded value, not the attempted new one.
    expect(result.current.view.resolved.design.wallMm).toBe(2.4);
    expect(result.current.error).toBe("disk full");
  });
});
