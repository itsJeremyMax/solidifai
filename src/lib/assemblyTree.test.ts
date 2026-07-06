import { describe, it, expect } from "vitest";
import { buildAssemblyTree, descendantIds, leafLabel, subtreeIdsForId } from "./assemblyTree";

const objs = (ids: string[]) => ids.map((id) => ({ id, name: leafLabel(id) }));

describe("assemblyTree", () => {
  it("builds a nested tree from slash path ids", () => {
    const t = buildAssemblyTree(objs(["base", "lid", "hinge/pin", "hinge/knuckle"]));
    expect(t.map((n) => n.id)).toEqual(["base", "lid", "hinge"]);
    const hinge = t.find((n) => n.id === "hinge")!;
    expect(hinge.isLeaf).toBe(false);
    expect(hinge.children.map((c) => c.id)).toEqual(["hinge/pin", "hinge/knuckle"]);
    expect(hinge.children[0].isLeaf).toBe(true);
    expect(t.find((n) => n.id === "base")!.isLeaf).toBe(true);
  });

  it("single flat part is a one-node tree (single-part case unchanged)", () => {
    const t = buildAssemblyTree(objs(["Bracket"]));
    expect(t.length).toBe(1);
    expect(t[0].isLeaf).toBe(true);
    expect(t[0].id).toBe("Bracket");
  });

  it("descendantIds returns the node itself for a leaf, all leaves under a group", () => {
    const t = buildAssemblyTree(objs(["base", "hinge/pin", "hinge/knuckle"]));
    expect(descendantIds(t, "base")).toEqual(["base"]);
    expect(descendantIds(t, "hinge").sort()).toEqual(["hinge/knuckle", "hinge/pin"]);
  });

  it("leafLabel shows the last path segment", () => {
    expect(leafLabel("hinge/pin")).toBe("pin");
    expect(leafLabel("base")).toBe("base");
  });

  it("deep nesting (3 levels) groups correctly", () => {
    const t = buildAssemblyTree(objs(["arm/wrist/bolt", "arm/wrist/nut", "arm/elbow"]));
    const arm = t[0];
    expect(arm.id).toBe("arm");
    const wrist = arm.children.find((c) => c.id === "arm/wrist")!;
    expect(wrist.children.map((c) => c.id).sort()).toEqual(["arm/wrist/bolt", "arm/wrist/nut"]);
    expect(descendantIds(t, "arm").sort()).toEqual([
      "arm/elbow",
      "arm/wrist/bolt",
      "arm/wrist/nut",
    ]);
  });

  it("descendantIds returns [] for an unknown id", () => {
    const t = buildAssemblyTree(objs(["base", "hinge/pin"]));
    expect(descendantIds(t, "missing")).toEqual([]);
  });

  it("subtreeIdsForId matches a leaf or all of a group's descendants (flat list)", () => {
    const ids = ["base", "hinge/pin", "hinge/knuckle"];
    expect(subtreeIdsForId(ids, "base")).toEqual(["base"]);
    expect(subtreeIdsForId(ids, "hinge").sort()).toEqual(["hinge/knuckle", "hinge/pin"]);
  });

  it("subtreeIdsForId does not match a sibling that merely shares a name prefix", () => {
    // "hinge" must not match "hingeplate"; only an exact id or a real path child.
    const ids = ["hinge/pin", "hingeplate"];
    expect(subtreeIdsForId(ids, "hinge")).toEqual(["hinge/pin"]);
  });
});
