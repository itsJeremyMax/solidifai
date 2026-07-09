import { describe, expect, it } from "vitest";
import type { ModelObject } from "../../lib/artifacts";
import { subtreeIndexForId, subtreeIndicesForId } from "./sceneGraph";

const objs = [{ id: "a" }, { id: "b" }, { id: "c" }] as unknown as ModelObject[];

describe("sceneGraph id lookup", () => {
  it("subtreeIndexForId finds the ordinal", () => {
    expect(subtreeIndexForId(objs, "b")).toBe(1);
    expect(subtreeIndexForId(objs, "zzz")).toBe(-1);
    expect(subtreeIndexForId(undefined, "a")).toBe(-1);
  });
  it("subtreeIndicesForId returns empty for null id", () => {
    expect(subtreeIndicesForId(objs, null)).toEqual([]);
  });

  it("field-aware payload: an instanced part co-selects only its real occurrences", () => {
    // `wheel` placed twice; the 2nd body carries the engine's exact occurrence
    // identity. A DIFFERENT part legitimately named `wheel_2` sits alongside it.
    const scene = [
      { id: "wheel/wheel" },
      { id: "wheel_2/wheel", occurrenceOf: "wheel/wheel", occurrenceIndex: 2 },
      { id: "wheel_2/hub" }, // real part named "wheel_2" — must NOT co-select
    ] as unknown as ModelObject[];
    // Selecting the instanced part lights up both placements, never the impostor.
    expect(subtreeIndicesForId(scene, "wheel")).toEqual([0, 1]);
    // Selecting the real `wheel_2` part lights up only itself.
    expect(subtreeIndicesForId(scene, "wheel_2/hub")).toEqual([2]);
  });

  it("older payload (no field): falls back to the _N slug heuristic", () => {
    // No object carries occurrenceOf, so we cannot tell an occurrence from a real
    // `_N` part; preserve the legacy heuristic (selecting `wheel` grabs `wheel_2`).
    const scene = [
      { id: "wheel/wheel" },
      { id: "wheel_2/wheel" },
      { id: "arm/arm" },
    ] as unknown as ModelObject[];
    expect(subtreeIndicesForId(scene, "wheel")).toEqual([0, 1]);
  });
});
