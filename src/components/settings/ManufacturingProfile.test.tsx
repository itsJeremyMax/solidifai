// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
vi.mock("../../lib/manufacturingProfile");
vi.mock("../../lib/workspaces", async (o) => ({
  ...(await o<typeof import("../../lib/workspaces")>()),
  getActiveWorkspace: vi.fn(),
}));
import * as ipc from "../../lib/manufacturingProfile";
import { getActiveWorkspace } from "../../lib/workspaces";
import ManufacturingProfile from "./ManufacturingProfile";

const view = (resolved: unknown, overrides: unknown = {}) => ({
  resolved,
  overrides,
  globalOverrides: {},
  material: { id: "pla", label: "PLA" },
});

describe("ManufacturingProfile", () => {
  beforeEach(() => {
    vi.mocked(getActiveWorkspace).mockResolvedValue({
      name: "Demo",
      path: "/ws/demo",
    } as Awaited<ReturnType<typeof getActiveWorkspace>>);
    vi.mocked(ipc.getWorkspaceProfile).mockResolvedValue(
      view(
        {
          design: { fit: "normal", wallMm: 2.4, filletMm: 1.0, minFeatureMm: 1.0 },
          fits: { looseMm: 0.4, normalMm: 0.2, tightMm: 0.1 },
          process: { kind: "fdm", nozzleMm: 0.4, layerMm: 0.2, overhangDeg: 45, infillPct: 20 },
          fabrication: { nozzleTempC: 210, bedTempC: 60, filamentCostPerKg: 25 },
        },
        { design: { wallMm: 2.4 } },
      ) as Awaited<ReturnType<typeof ipc.getWorkspaceProfile>>,
    );
  });
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders groups + echoes material + marks an override as set-here", async () => {
    render(<ManufacturingProfile scope="workspace" />);
    expect(await screen.findByText("Design")).toBeTruthy();
    expect(screen.getByText("Fabrication")).toBeTruthy();
    expect(screen.getByText("PLA")).toBeTruthy();
    // the wall field is overridden in this workspace -> a reset control is present
    await waitFor(() => expect(screen.getAllByText(/reset/i).length).toBeGreaterThan(0));
  });

  it("global scope loads the global profile with no workspace", async () => {
    vi.mocked(getActiveWorkspace).mockResolvedValue(
      null as Awaited<ReturnType<typeof getActiveWorkspace>>,
    );
    vi.mocked(ipc.getGlobalProfile).mockResolvedValue(
      view({
        design: { fit: "normal", wallMm: 2, filletMm: 1, minFeatureMm: 1 },
        fits: { looseMm: 0.4, normalMm: 0.2, tightMm: 0.1 },
        process: { kind: "fdm", nozzleMm: 0.4, layerMm: 0.2, overhangDeg: 45, infillPct: 20 },
        fabrication: { nozzleTempC: 210, bedTempC: 60, filamentCostPerKg: 25 },
      }) as Awaited<ReturnType<typeof ipc.getGlobalProfile>>,
    );
    render(<ManufacturingProfile scope="global" />);
    expect(await screen.findByText("Design")).toBeTruthy();
    expect(ipc.getGlobalProfile).toHaveBeenCalled();
  });

  it("editing a number auto-saves via the hook", async () => {
    vi.mocked(ipc.setWorkspaceProfile).mockResolvedValue(
      view({ design: { wallMm: 3 } }, { design: { wallMm: 3 } }) as Awaited<
        ReturnType<typeof ipc.setWorkspaceProfile>
      >,
    );
    render(<ManufacturingProfile scope="workspace" />);
    const wall = await screen.findByLabelText("Wall thickness");
    fireEvent.change(wall, { target: { value: "3" } });
    fireEvent.blur(wall);
    await waitFor(() =>
      expect(ipc.setWorkspaceProfile).toHaveBeenCalledWith({ design: { wallMm: 3 } }, []),
    );
  });

  it("clearing a field skips the write and snaps back to the prior value", async () => {
    render(<ManufacturingProfile scope="workspace" />);
    const wall = (await screen.findByLabelText("Wall thickness")) as HTMLInputElement;
    expect(wall.value).toBe("2.4");
    fireEvent.change(wall, { target: { value: "" } });
    fireEvent.blur(wall);
    expect(ipc.setWorkspaceProfile).not.toHaveBeenCalled(); // no empty -> 0 write
    expect(wall.value).toBe("2.4"); // restored on the skip path
  });

  it("blurring an unchanged value does not write", async () => {
    render(<ManufacturingProfile scope="workspace" />);
    const wall = await screen.findByLabelText("Wall thickness");
    fireEvent.blur(wall); // same value still in the field
    expect(ipc.setWorkspaceProfile).not.toHaveBeenCalled();
  });
});
