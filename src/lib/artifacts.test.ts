import { describe, expect, it } from "vitest";

import { parseModelInfo } from "./artifacts";

function baseModel(objectExtra: Record<string, unknown>) {
  return JSON.stringify({
    schema: 2,
    buildId: 1,
    units: "mm",
    build: { ok: true, durationMs: 1, warnings: [] },
    objects: [
      {
        id: "body",
        name: "Body",
        kind: "Solid",
        node: "body",
        visible: true,
        ...objectExtra,
      },
    ],
    bbox: { size: [1, 1, 1], min: [0, 0, 0], max: [1, 1, 1] },
    volume: 1,
    centerOfMass: [0, 0, 0],
    mass: { value: 1, material: "PLA", density: 1.24 },
    valid: true,
    manifold: true,
    params: { schema: {}, values: {} },
  });
}

describe("parseModelInfo with import fields", () => {
  it("passes role and appearance.opacity through", () => {
    const m = parseModelInfo(
      baseModel({
        role: "reference",
        appearance: {
          material: "pla",
          baseColor: [0.5, 0.5, 0.5],
          metalness: 0,
          roughness: 0.6,
          clearcoat: 0,
          clearcoatRoughness: 0,
          opacity: 0.35,
        },
        mass: null,
      }),
    );
    expect(m).not.toBeNull();
    expect(m!.objects[0].role).toBe("reference");
    expect(m!.objects[0].appearance?.opacity).toBe(0.35);
    expect(m!.objects[0].mass).toBeNull();
  });

  it("tolerates absence of role/opacity (legacy objects)", () => {
    const m = parseModelInfo(baseModel({}));
    expect(m).not.toBeNull();
    expect(m!.objects[0].role).toBeUndefined();
  });
});
