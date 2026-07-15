import { test, expect } from "vitest";

import { FORMATS, defaultOptions, qualityTolerance, UNIT_OPTIONS } from "./exportSchema";

test("FORMATS lists every engine export format", () => {
  expect(FORMATS.map((f) => f.key)).toEqual(["step", "stl", "glb", "gltf", "brep", "3mf"]);
});

test("STL defaults are binary + standard quality", () => {
  const o = defaultOptions("stl");
  expect(o.ascii).toBe(false);
  expect(o.quality).toBe("standard");
  expect(o.tolerance).toBe(0.01);
});

test("BREP has no options", () => {
  expect(defaultOptions("brep")).toEqual({});
});

test("qualityTolerance maps presets per format", () => {
  expect(qualityTolerance("stl", "draft")).toBe(0.05);
  expect(qualityTolerance("glb", "fine")).toBe(0.0005);
});

test("UNIT_OPTIONS leads with mm", () => {
  expect(UNIT_OPTIONS[0].value).toBe("mm");
});
