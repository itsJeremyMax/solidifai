import { describe, it, expect } from "vitest";

import {
  slug,
  slugPath,
  occurrencePrefixes,
  parseAssemblyTree,
  deriveOccurrenceFamilies,
  deriveJoints,
} from "./assemblyMeta";

/** A rig: `wheel` placed 3 times (the third mirrored), `arm` placed once, and a
 *  revolute joint on the root skeleton. Mirrors the engine's get_assembly_tree
 *  shape (raw child ids, `shape_inputs` snake_case, occurrences [{frame,mirror}]). */
const RIG = {
  ok: true,
  tree: {
    skeleton: {
      params: {},
      scalars: ["gap"],
      frames: ["hub_a", "hub_b", "hub_c", "pivot"],
      shapes: [],
      joints: [
        {
          name: "hinge",
          kind: "revolute",
          frame: "pivot",
          axis: [0, 0, 1],
          limits: [0, 120],
          between: ["arm", "post"],
        },
      ],
    },
    children: [
      {
        id: "wheel",
        kind: "part",
        source: "parts/wheel.py",
        attach: "hub_a",
        inputs: [],
        shape_inputs: [],
        occurrences: [
          { frame: "hub_a", mirror: null },
          { frame: "hub_b", mirror: null },
          { frame: "hub_c", mirror: "yz" },
        ],
      },
      {
        id: "arm",
        kind: "part",
        source: "parts/arm.py",
        attach: "pivot",
        inputs: ["gap"],
        shape_inputs: [],
        occurrences: [{ frame: "pivot", mirror: null }],
      },
    ],
  },
};

describe("slug / prefixes", () => {
  it("slugs @ to _ and lowercases, matching the engine", () => {
    expect(slug("wheel@2")).toBe("wheel_2");
    expect(slug("My-Part")).toBe("my_part");
    expect(slug("Gnomon")).toBe("gnomon");
  });

  it("slugs each path segment independently", () => {
    expect(slugPath("hinge/pin@2")).toBe("hinge/pin_2");
    expect(slugPath("Arm/Wrist")).toBe("arm/wrist");
  });

  it("occurrencePrefixes keeps the first bare, then @2, @3", () => {
    expect(occurrencePrefixes("wheel", 3)).toEqual(["wheel", "wheel@2", "wheel@3"]);
    expect(occurrencePrefixes("wheel", 1)).toEqual(["wheel"]);
    expect(occurrencePrefixes("wheel", 0)).toEqual(["wheel"]);
  });
});

describe("parseAssemblyTree", () => {
  it("returns null for empty, malformed, ok:false, or missing tree", () => {
    expect(parseAssemblyTree(null)).toBeNull();
    expect(parseAssemblyTree("{not json")).toBeNull();
    expect(
      parseAssemblyTree(JSON.stringify({ ok: false, error: "not an assembly workspace" })),
    ).toBeNull();
    expect(parseAssemblyTree(JSON.stringify({ ok: true }))).toBeNull();
  });

  it("parses skeleton + children defensively", () => {
    const meta = parseAssemblyTree(JSON.stringify(RIG))!;
    expect(meta).not.toBeNull();
    expect(meta.skeleton?.scalars).toEqual(["gap"]);
    expect(meta.skeleton?.joints[0].name).toBe("hinge");
    expect(meta.children.map((c) => c.id)).toEqual(["wheel", "arm"]);
    expect(meta.children[0].shapeInputs).toEqual([]);
    expect(meta.children[0].occurrences[2].mirror).toBe("yz");
  });

  it("drops a child with no id and a bad mirror value", () => {
    const meta = parseAssemblyTree(
      JSON.stringify({
        ok: true,
        tree: {
          skeleton: null,
          children: [
            { kind: "part" }, // no id -> dropped
            { id: "x", occurrences: [{ frame: "f", mirror: "diagonal" }] },
          ],
        },
      }),
    )!;
    expect(meta.children.map((c) => c.id)).toEqual(["x"]);
    expect(meta.children[0].occurrences[0].mirror).toBeNull();
  });
});

describe("deriveOccurrenceFamilies", () => {
  it("makes one family per instanced part, keyed by primary slug", () => {
    const meta = parseAssemblyTree(JSON.stringify(RIG));
    const fams = deriveOccurrenceFamilies(meta);
    expect([...fams.keys()]).toEqual(["wheel"]); // arm placed once -> no family
    const wheel = fams.get("wheel")!;
    expect(wheel.displayBase).toBe("wheel");
    expect(wheel.memberIds).toEqual(["wheel", "wheel_2", "wheel_3"]);
    expect(wheel.occurrences.map((o) => o.label)).toEqual(["wheel", "wheel@2", "wheel@3"]);
    expect(wheel.occurrences.map((o) => o.frame)).toEqual(["hub_a", "hub_b", "hub_c"]);
    expect(wheel.occurrences[2].mirror).toBe("yz");
  });

  it("finds nested occurrences along the primary path", () => {
    const meta = parseAssemblyTree(
      JSON.stringify({
        ok: true,
        tree: {
          skeleton: { scalars: [], frames: ["mount"], shapes: [], joints: [] },
          children: [
            {
              id: "hinge",
              kind: "assembly",
              attach: "mount",
              inputs: [],
              shape_inputs: [],
              occurrences: [{ frame: "mount", mirror: null }],
              skeleton: { scalars: [], frames: ["p"], shapes: [], joints: [] },
              children: [
                {
                  id: "pin",
                  kind: "part",
                  attach: "p",
                  inputs: [],
                  shape_inputs: [],
                  occurrences: [
                    { frame: "p", mirror: null },
                    { frame: "p2", mirror: null },
                  ],
                },
              ],
            },
          ],
        },
      }),
    );
    const fams = deriveOccurrenceFamilies(meta);
    expect([...fams.keys()]).toEqual(["hinge/pin"]);
    expect(fams.get("hinge/pin")!.memberIds).toEqual(["hinge/pin", "hinge/pin_2"]);
  });

  it("returns an empty map for null meta", () => {
    expect(deriveOccurrenceFamilies(null).size).toBe(0);
  });
});

describe("deriveJoints", () => {
  it("lists root joints by bare name", () => {
    const joints = deriveJoints(parseAssemblyTree(JSON.stringify(RIG)));
    expect(joints).toHaveLength(1);
    expect(joints[0].displayName).toBe("hinge");
    expect(joints[0].kind).toBe("revolute");
    expect(joints[0].limits).toEqual([0, 120]);
    expect(joints[0].between).toEqual(["arm", "post"]);
  });

  it("path-qualifies sub-assembly joints", () => {
    const joints = deriveJoints(
      parseAssemblyTree(
        JSON.stringify({
          ok: true,
          tree: {
            skeleton: { scalars: [], frames: [], shapes: [], joints: [] },
            children: [
              {
                id: "arm",
                kind: "assembly",
                attach: null,
                inputs: [],
                shape_inputs: [],
                occurrences: [{ frame: null, mirror: null }],
                skeleton: {
                  scalars: [],
                  frames: ["p"],
                  shapes: [],
                  joints: [{ name: "swing", kind: "revolute", frame: "p" }],
                },
                children: [],
              },
            ],
          },
        }),
      ),
    );
    expect(joints.map((j) => j.displayName)).toEqual(["arm/swing"]);
  });
});
