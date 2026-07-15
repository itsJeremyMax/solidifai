import { describe, expect, it } from "vitest";

import { projectBuildBrief } from "./useBuildBrief";

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
});
