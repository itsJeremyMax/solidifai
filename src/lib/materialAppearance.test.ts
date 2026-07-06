/**
 * Tests for the shared appearance module (engine mirror of FINISH_PRESETS +
 * base metalness + sRGB->linear). The finish numbers here MUST stay identical
 * to engine `FINISH_PRESETS`, so these lock the mapping down.
 */
import { describe, it, expect } from "vitest";

import { appearanceFor, hexToLinear, appearanceHash } from "./materialAppearance";

describe("materialAppearance", () => {
  it("decodes sRGB hex to linear (mid-gray)", () => {
    const [r] = hexToLinear("#808080");
    expect(Math.abs(r - 0.2158)).toBeLessThan(1e-3);
  });

  it("satin plastic keeps base metalness 0 and uses satin roughness", () => {
    const a = appearanceFor({
      id: "x",
      label: "X",
      base: "pla",
      colorHex: "#2b6cff",
      finish: "satin",
    });
    expect(a.metalness).toBe(0);
    expect(Math.abs(a.roughness - 0.55)).toBeLessThan(1e-5);
    expect(Math.abs(a.clearcoat - 0.1)).toBeLessThan(1e-5);
  });

  it("metallic finish forces metalness to 1", () => {
    const a = appearanceFor({
      id: "x",
      label: "X",
      base: "aluminum",
      colorHex: "#d6d9de",
      finish: "metallic",
    });
    expect(a.metalness).toBe(1);
    expect(Math.abs(a.roughness - 0.35)).toBeLessThan(1e-5);
  });

  it("hash is stable across object identity but changes with finish", () => {
    const base = {
      id: "x",
      label: "X",
      base: "pla",
      colorHex: "#2b6cff",
      finish: "satin",
    } as const;
    expect(appearanceHash(base)).toBe(appearanceHash({ ...base }));
    expect(appearanceHash(base)).not.toBe(appearanceHash({ ...base, finish: "gloss" }));
  });
});
