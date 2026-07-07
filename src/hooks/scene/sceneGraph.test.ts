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
});
