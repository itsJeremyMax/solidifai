import { describe, it, expect } from "vitest";

import {
  isSolidPart,
  parseMeasureReport,
  parseStressReport,
  parseToleranceResult,
} from "./validation";

describe("parseMeasureReport", () => {
  it("accepts a well-formed report", () => {
    const raw = JSON.stringify({
      ok: true,
      schema: 1,
      buildId: 3,
      parts: [{ partId: "a", partName: "A", mass: 1.2 }],
      total: { mass: 1.2, volume: 1000, centerOfMass: [0, 0, 0], inertia: null },
      summary: { parts: 1, mass: 1.2, unit: "g" },
    });
    expect(parseMeasureReport(raw)?.total.mass).toBe(1.2);
  });

  it("rejects an error envelope and garbage", () => {
    expect(parseMeasureReport(JSON.stringify({ ok: false, error: "no model" }))).toBeNull();
    expect(parseMeasureReport("not json")).toBeNull();
  });
});

describe("isSolidPart", () => {
  it("separates solids from references", () => {
    expect(isSolidPart({ partId: "a", partName: "A", mass: 2 } as never)).toBe(true);
    expect(isSolidPart({ partId: "r", partName: "R", role: "reference" })).toBe(false);
  });
});

describe("parseStressReport", () => {
  it("accepts a report and rejects garbage", () => {
    const raw = JSON.stringify({
      ok: true,
      schema: 1,
      buildId: 1,
      parts: [{ partId: "a", partName: "A", hotspots: [] }],
      summary: { warning: 0, advisory: 0, parts: 1 },
    });
    expect(parseStressReport(raw)?.summary.parts).toBe(1);
    expect(parseStressReport("{}")).toBeNull();
  });
});

describe("parseToleranceResult", () => {
  it("accepts a fit result and rejects an error", () => {
    const raw = JSON.stringify({
      ok: true,
      nominal: 0,
      worstCase: { min: 0.005, max: 0.029, range: 0.024 },
      rss: { min: 0.01, max: 0.02, range: 0.01 },
      fit: { type: "clearance", minGap: 0.005, maxGap: 0.029 },
      links: [],
    });
    expect(parseToleranceResult(raw)?.fit?.type).toBe("clearance");
    expect(parseToleranceResult(JSON.stringify({ ok: false, error: "bad" }))).toBeNull();
  });
});
