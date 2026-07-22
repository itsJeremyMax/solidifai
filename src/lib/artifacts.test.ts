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

describe("parseModelInfo empty publications", () => {
  it("accepts an empty publication with null extents", () => {
    const empty = JSON.stringify({
      ...JSON.parse(baseModel({})),
      objects: [],
      bbox: null,
      centerOfMass: null,
      volume: 0,
      mass: { value: 0, material: "PLA", density: 1.24 },
    });

    expect(parseModelInfo(empty)?.objects).toEqual([]);
  });

  it("rejects a non-empty manifest with null extents", () => {
    const malformed = JSON.stringify({
      ...JSON.parse(baseModel({})),
      bbox: null,
      centerOfMass: null,
    });

    expect(parseModelInfo(malformed)).toBeNull();
  });
});

describe("parseModelInfo params", () => {
  it("keeps boolean and enum schema entries plus matching values", () => {
    const parsed = parseModelInfo(
      JSON.stringify({
        ...JSON.parse(baseModel({})),
        params: {
          schema: {
            size: { value: 20, min: 5, max: 100, step: 1, unit: "mm", desc: "Edge length" },
            enabled: { type: "boolean", value: true, desc: "Show the full body" },
            mode: {
              type: "enum",
              value: "draft",
              choices: ["draft", "final"],
              desc: "Output mode",
            },
          },
          values: { size: 20, enabled: true, mode: "draft" },
        },
      }),
    );

    expect(parsed?.params).toEqual({
      schema: {
        size: { value: 20, min: 5, max: 100, step: 1, unit: "mm", desc: "Edge length" },
        enabled: { type: "boolean", value: true, desc: "Show the full body" },
        mode: {
          type: "enum",
          value: "draft",
          choices: ["draft", "final"],
          desc: "Output mode",
        },
      },
      values: { size: 20, enabled: true, mode: "draft" },
    });
  });

  it("drops malformed typed schema entries and their values", () => {
    const parsed = parseModelInfo(
      JSON.stringify({
        ...JSON.parse(baseModel({})),
        params: {
          schema: {
            enabled: { type: "boolean", value: "yes", desc: "Broken" },
            mode: { type: "enum", value: "draft", choices: ["draft", 1], desc: "Broken" },
          },
          values: { enabled: true, mode: "draft" },
        },
      }),
    );

    expect(parsed?.params).toEqual({ schema: {}, values: {} });
  });

  it("keeps legacy numeric schema entries even when they carry extra type metadata", () => {
    const parsed = parseModelInfo(
      JSON.stringify({
        ...JSON.parse(baseModel({})),
        params: {
          schema: {
            hole_dia: {
              type: "diameter",
              value: 5,
              min: 1,
              max: 20,
              step: 0.5,
              unit: "mm",
              desc: "Through hole diameter",
            },
          },
          values: { hole_dia: 6 },
        },
      }),
    );

    expect(parsed?.params).toEqual({
      schema: {
        hole_dia: {
          type: "diameter",
          value: 5,
          min: 1,
          max: 20,
          step: 0.5,
          unit: "mm",
          desc: "Through hole diameter",
        },
      },
      values: { hole_dia: 6 },
    });
  });

  it("keeps legacy numeric values when reserved type names are only metadata", () => {
    const parsed = parseModelInfo(
      JSON.stringify({
        ...JSON.parse(baseModel({})),
        params: {
          schema: {
            size: {
              type: "boolean",
              value: 5,
              min: 1,
              max: 10,
              step: 1,
              unit: "mm",
              desc: "Legacy metadata",
            },
          },
          values: { size: 7 },
        },
      }),
    );

    expect(parsed?.params.values).toEqual({ size: 7 });
  });

  it("drops prototype-sensitive parameter keys and inherited-name values", () => {
    const manifest = JSON.parse(baseModel({}));
    manifest.params = {
      schema: JSON.parse(
        '{"__proto__":{"value":1,"min":0,"max":2,"step":1,"unit":"","desc":""},' +
          '"constructor":{"value":1,"min":0,"max":2,"step":1,"unit":"","desc":""},' +
          '"safe":{"value":1,"min":0,"max":2,"step":1,"unit":"","desc":""}}',
      ),
      values: JSON.parse('{"__proto__":1,"constructor":1,"toString":1,"safe":2}'),
    };

    const parsed = parseModelInfo(JSON.stringify(manifest));

    expect(parsed?.params.schema).toEqual({
      safe: { value: 1, min: 0, max: 2, step: 1, unit: "", desc: "" },
    });
    expect(parsed?.params.values).toEqual({ safe: 2 });
    expect(Object.getPrototypeOf(parsed!.params.schema)).toBeNull();
    expect(Object.getPrototypeOf(parsed!.params.values)).toBeNull();
  });

  it("still rejects unknown typed declarations when their value is not numeric", () => {
    const parsed = parseModelInfo(
      JSON.stringify({
        ...JSON.parse(baseModel({})),
        params: {
          schema: {
            hidden: { type: "bool", value: false, desc: "Hidden flag" },
            mode: { type: "choice", value: "draft", desc: "Hidden enum" },
          },
          values: { hidden: false, mode: "draft" },
        },
      }),
    );

    expect(parsed?.params).toEqual({ schema: {}, values: {} });
  });
});
