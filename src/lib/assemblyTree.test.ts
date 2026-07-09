import { describe, it, expect } from "vitest";
import {
  buildAssemblyTree,
  descendantIds,
  idMatchesBase,
  leafLabel,
  subtreeIdsForId,
} from "./assemblyTree";
import type { OccurrenceFamily } from "./assemblyMeta";

const objs = (ids: string[]) => ids.map((id) => ({ id, name: leafLabel(id) }));

/** A one-family map for `wheel` placed 3 times, as deriveOccurrenceFamilies emits. */
const wheelFamilies = () =>
  new Map<string, OccurrenceFamily>([
    [
      "wheel",
      {
        primaryId: "wheel",
        displayBase: "wheel",
        memberIds: ["wheel", "wheel_2", "wheel_3"],
        occurrences: [
          { frame: "hub_a", mirror: null, label: "wheel" },
          { frame: "hub_b", mirror: null, label: "wheel@2" },
          { frame: "hub_c", mirror: "yz", label: "wheel@3" },
        ],
        isAssembly: false,
      },
    ],
  ]);

/** A one-family map for an instanced SUB-assembly `rig` placed twice, each
 *  containing a part `blk` (real per-instance internals in the geometry). */
const rigFamilies = () =>
  new Map<string, OccurrenceFamily>([
    [
      "rig",
      {
        primaryId: "rig",
        displayBase: "rig",
        memberIds: ["rig", "rig_2"],
        occurrences: [
          { frame: "a", mirror: null, label: "rig" },
          { frame: "b", mirror: "yz", label: "rig@2" },
        ],
        isAssembly: true,
      },
    ],
  ]);

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

  it("subtreeIdsForId includes slugged occurrence siblings of an instanced part", () => {
    const ids = ["wheel/wheel", "wheel_2/wheel", "wheel_3/wheel", "arm/arm"];
    expect(subtreeIdsForId(ids, "wheel").sort()).toEqual([
      "wheel/wheel",
      "wheel_2/wheel",
      "wheel_3/wheel",
    ]);
  });
});

describe("idMatchesBase", () => {
  it("matches the exact id, path descendants, and occurrence siblings", () => {
    expect(idMatchesBase("wheel", "wheel")).toBe(true);
    expect(idMatchesBase("wheel/wheel", "wheel")).toBe(true);
    expect(idMatchesBase("wheel_2/wheel", "wheel")).toBe(true);
    expect(idMatchesBase("wheel_10", "wheel")).toBe(true);
  });

  it("does not match unrelated name-prefix siblings", () => {
    expect(idMatchesBase("wheelbarrow", "wheel")).toBe(false);
    expect(idMatchesBase("hingeplate", "hinge")).toBe(false);
    expect(idMatchesBase("wheel_x", "wheel")).toBe(false); // '_' then non-digit
  });

  it("uses the exact occurrenceOf field when present", () => {
    // The occurrence body names its primary counterpart; match by that, not slug.
    expect(idMatchesBase("wheel_2/wheel", "wheel", "wheel/wheel")).toBe(true);
    expect(idMatchesBase("rig_2/blk/blk", "rig", "rig/blk/blk")).toBe(true);
    // The field points elsewhere -> not a sibling of this base.
    expect(idMatchesBase("wheel_2/wheel", "arm", "wheel/wheel")).toBe(false);
  });

  it("field-aware payload: a real _N part is not treated as an occurrence", () => {
    // A body with no occurrenceOf, in a field-aware payload, is definitively NOT
    // an occurrence — the slug heuristic is skipped, so `wheel_2/hub` (a real part)
    // does not co-select with `wheel`.
    expect(idMatchesBase("wheel_2/hub", "wheel", null, /* fieldAware */ true)).toBe(false);
    // Same id in an OLD payload still matches via the heuristic (documented fallback).
    expect(idMatchesBase("wheel_2/hub", "wheel", null, /* fieldAware */ false)).toBe(true);
  });
});

describe("buildAssemblyTree with occurrence families", () => {
  const objects = objs(["wheel/wheel", "wheel_2/wheel", "wheel_3/wheel", "arm/arm"]);

  it("folds an instanced part's placements into one badged node", () => {
    const tree = buildAssemblyTree(objects, wheelFamilies());
    expect(tree.map((n) => n.id)).toEqual(["wheel", "arm"]); // wheel_2/wheel_3 absorbed
    const wheel = tree.find((n) => n.id === "wheel")!;
    expect(wheel.occurrences).toHaveLength(3);
    expect(wheel.label).toBe("wheel");
    expect(wheel.occLeafIds!.sort()).toEqual(["wheel/wheel", "wheel_2/wheel", "wheel_3/wheel"]);
  });

  it("descendantIds on a family returns every placement's object id", () => {
    const tree = buildAssemblyTree(objects, wheelFamilies());
    expect(descendantIds(tree, "wheel").sort()).toEqual([
      "wheel/wheel",
      "wheel_2/wheel",
      "wheel_3/wheel",
    ]);
  });

  it("renders unchanged when no families are given", () => {
    const tree = buildAssemblyTree(objects);
    expect(tree.map((n) => n.id)).toEqual(["wheel", "wheel_2", "wheel_3", "arm"]);
  });
});

describe("buildAssemblyTree with an instanced sub-assembly", () => {
  // Two placements of `rig`, each with its own `blk` body under a distinct path.
  const objects = objs(["rig/blk/blk", "rig_2/blk/blk"]);

  it("nests each placement's internals under the badged family node", () => {
    const tree = buildAssemblyTree(objects, rigFamilies());
    expect(tree.map((n) => n.id)).toEqual(["rig"]);
    const rig = tree[0];
    expect(rig.occurrences).toHaveLength(2);
    expect(rig.occAssembly).toBe(true);
    // One group per placement, each carrying its real internals (not a flat list).
    expect(rig.children.map((c) => c.id)).toEqual(["rig", "rig_2"]);
    expect(rig.children[0].occInfo!.label).toBe("rig");
    expect(rig.children[1].occInfo!.mirror).toBe("yz");
    // The primary placement's internal blk body is present and reachable.
    expect(rig.children[0].children.map((c) => c.id)).toEqual(["rig/blk"]);
    expect(rig.children[1].children[0].children.map((c) => c.id)).toEqual(["rig_2/blk/blk"]);
  });

  it("selection/visibility still span every placement's bodies (occLeafIds)", () => {
    const tree = buildAssemblyTree(objects, rigFamilies());
    expect(descendantIds(tree, "rig").sort()).toEqual(["rig/blk/blk", "rig_2/blk/blk"]);
  });
});
