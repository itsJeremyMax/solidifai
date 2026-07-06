import * as THREE from "three";
import { describe, expect, it } from "vitest";

import { DEFAULT_APPEARANCE, materialFromAppearance } from "./materials";

describe("materialFromAppearance ghosting", () => {
  it("is opaque by default", () => {
    const m = materialFromAppearance(DEFAULT_APPEARANCE);
    expect(m.transparent).toBe(false);
    expect(m.opacity).toBe(1);
  });

  it("ghosts a reference (opacity < 1): transparent, double-sided, no depth write", () => {
    const m = materialFromAppearance({ ...DEFAULT_APPEARANCE, opacity: 0.35 });
    expect(m.transparent).toBe(true);
    expect(m.opacity).toBeCloseTo(0.35);
    expect(m.side).toBe(THREE.DoubleSide);
    expect(m.depthWrite).toBe(false);
  });

  it("stays opaque at opacity exactly 1", () => {
    const m = materialFromAppearance({ ...DEFAULT_APPEARANCE, opacity: 1 });
    expect(m.transparent).toBe(false);
    expect(m.side).toBe(THREE.FrontSide);
  });
});
