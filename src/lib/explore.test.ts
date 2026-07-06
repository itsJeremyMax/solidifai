import { describe, it, expect } from "vitest";

import { parseOptimizeResult, parseSweepReport } from "./explore";

describe("parseSweepReport", () => {
  it("accepts a sweep and rejects garbage", () => {
    const raw = JSON.stringify({
      ok: true,
      param: "size",
      unit: "mm",
      variants: [{ value: 10, ok: true, mass: 2, volume: 1000, bbox: [10, 10, 10] }],
    });
    expect(parseSweepReport(raw)?.variants[0].mass).toBe(2);
    expect(parseSweepReport(JSON.stringify({ ok: false }))).toBeNull();
    expect(parseSweepReport("x")).toBeNull();
  });
});

describe("parseOptimizeResult", () => {
  it("accepts a result and rejects garbage", () => {
    const raw = JSON.stringify({
      ok: true,
      param: "size",
      objective: "min_mass",
      best: { value: 10, ok: true, mass: 2, bbox: [10, 10, 10] },
      feasibleCount: 1,
      evaluated: [{ value: 10, ok: true, mass: 2 }],
    });
    expect(parseOptimizeResult(raw)?.best?.value).toBe(10);
    expect(parseOptimizeResult("{}")).toBeNull();
  });
});
