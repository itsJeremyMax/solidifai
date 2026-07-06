import { describe, expect, it } from "vitest";
import { isWebGLReadback, packReadbackRows } from "./readback";

/** Build a w×h RGBA8 buffer whose row index is encoded in every red byte. */
function rows(w: number, h: number, stride = w * 4): Uint8Array {
  const buf = new Uint8Array(stride * h);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) buf[y * stride + x * 4] = y;
  }
  return buf;
}

describe("packReadbackRows", () => {
  it("copies rows straight across for top-down (WebGPU) readback", () => {
    const out = packReadbackRows(rows(2, 3), 2, 3, false);
    expect(out[0]).toBe(0); // row 0 stays on top
    expect(out[2 * 4 * 2]).toBe(2); // row 2 stays at the bottom
  });

  it("flips rows vertically for bottom-up (WebGL) readback", () => {
    const out = packReadbackRows(rows(2, 3), 2, 3, true);
    expect(out[0]).toBe(2); // source bottom row lands on top
    expect(out[2 * 4 * 2]).toBe(0); // source top row lands at the bottom
  });

  it("strips a 256-byte padded stride, with and without the flip", () => {
    const w = 3; // 12 row bytes → padded to 256
    const straight = packReadbackRows(rows(w, 2, 256), w, 2, false);
    expect(straight.length).toBe(w * 4 * 2);
    expect(straight[0]).toBe(0);
    expect(straight[w * 4]).toBe(1);
    const flipped = packReadbackRows(rows(w, 2, 256), w, 2, true);
    expect(flipped[0]).toBe(1);
    expect(flipped[w * 4]).toBe(0);
  });
});

describe("isWebGLReadback", () => {
  it("keys on the backend's isWebGLBackend flag", () => {
    expect(isWebGLReadback({ backend: { isWebGLBackend: true } })).toBe(true);
    expect(isWebGLReadback({ backend: { isWebGPUBackend: true } })).toBe(false);
    expect(isWebGLReadback({ backend: {} })).toBe(false);
  });
});
