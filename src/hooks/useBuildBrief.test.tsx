import { describe, expect, it } from "vitest";

import { formatTrustItem, projectBuildBrief } from "./useBuildBrief";

describe("projectBuildBrief", () => {
  it("projects a v1 brief into safe display rows", () => {
    const projected = projectBuildBrief({
      schema: 1,
      summary: "box",
      tier: "stream",
      parts: [{ name: "base" }],
      key_dims: [],
      interfaces: [],
      make_real: "FDM",
    });

    expect(projected?.schema).toBe(1);
    expect(projected?.parts).toEqual([{ id: "base", name: "base", role: "", why: "" }]);
  });

  it("preserves v2 raw hierarchy and tolerates optional sections", () => {
    const raw = {
      schema: 2,
      revision: 3,
      summary: "assembly",
      tier: "pause",
      parts: [{ id: "base", name: "Base", children: ["magnet"] }],
      dimensions: [],
      interfaces: [],
      assumptions: [{ id: "risk", statement: "fit", risk: "high", disposition: "test" }],
    };

    const projected = projectBuildBrief(raw);

    expect(projected?.schema).toBe(2);
    expect(projected?.raw).toBe(raw);
    expect(projected?.interfaces).toEqual([]);
    expect(projected?.parts[0].children).toEqual(["magnet"]);
  });

  it("projects the v2 trust contract for inspection", () => {
    const projected = projectBuildBrief({
      schema: 2,
      revision: 1,
      summary: "assembly",
      tier: "pause",
      parts: [],
      dimensions: [],
      interfaces: [],
      references: [{ id: "board", required: true }],
      assumptions: [
        { id: "clearance", statement: "Verify clearance", risk: "high", disposition: "test" },
      ],
      requirements: [{ id: "wall", statement: "Wall thickness" }],
      obligations: [{ id: "verify", statement: "Run fit check" }],
      manufacturing: [{ description: "FDM prototype" }, { description: "CNC production" }],
    });

    expect(projected?.trust).toEqual({
      references: [{ id: "board", required: true }],
      assumptions: [
        { id: "clearance", statement: "Verify clearance", risk: "high", disposition: "test" },
      ],
      requirements: [{ id: "wall", statement: "Wall thickness" }],
      obligations: [{ id: "verify", statement: "Run fit check" }],
      manufacturing: ["FDM prototype", "CNC production"],
    });
  });

  it("formats trust metadata without hiding risk ownership", () => {
    expect(
      formatTrustItem("Assumption", {
        id: "fit",
        statement: "Verify clearance",
        risk: "high",
        disposition: "delegated",
        source: "user",
        rationale: "User owns fit",
      }),
    ).toEqual({
      label: "Assumption: Verify clearance",
      detail: "risk: high | disposition: delegated | source: user | User owns fit",
    });
  });
});
