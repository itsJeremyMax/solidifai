import { describe, expect, it } from "vitest";
import { CATALOG, processForBase, supportedProcesses } from "./materials";

describe("processForBase", () => {
  it("does not silently classify an unknown base as FDM", () => {
    expect(processForBase("moon-dust")).toBeUndefined();
  });

  it("resolves known metal bases to CNC", () => {
    expect(processForBase("aluminum")).toBe("cnc");
  });

  it("derives process and supported IDs from the shared catalog", () => {
    expect(processForBase("aluminum")).toBe(CATALOG.bases.aluminum.defaultProcess);
    expect(supportedProcesses()).toEqual(Object.keys(CATALOG.processes));
  });
});
