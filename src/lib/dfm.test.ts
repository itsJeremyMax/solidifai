import { describe, expect, it } from "vitest";

import { parseDfmReport, DFM_SEVERITIES } from "./dfm";

const VALID = JSON.stringify({
  ok: true,
  schema: 1,
  buildId: 7,
  parts: [
    {
      partId: "plate",
      partName: "Plate",
      process: "fdm",
      evaluated: true,
      violations: [
        {
          rule: "wall_thickness",
          severity: "critical",
          message: "Wall ~0.6 mm is below the 0.8 mm FDM minimum.",
          measured: { value: 0.6, unit: "mm" },
          threshold: { value: 0.8, unit: "mm" },
          location: [1, 2, 3],
          source: "dfm-additive.md",
          sampled: true,
          hint: "Thicken it.",
        },
      ],
    },
  ],
  summary: { critical: 1, warning: 0, advisory: 0, parts: 1 },
});

describe("parseDfmReport", () => {
  it("parses a valid report", () => {
    const r = parseDfmReport(VALID);
    expect(r).not.toBeNull();
    expect(r!.buildId).toBe(7);
    expect(r!.parts[0].partId).toBe("plate");
    expect(r!.parts[0].violations[0].severity).toBe("critical");
    expect(r!.summary.critical).toBe(1);
  });

  it("returns null for an engine error envelope", () => {
    expect(parseDfmReport(JSON.stringify({ ok: false, error: "no model" }))).toBeNull();
  });

  it("returns null for unparseable text", () => {
    expect(parseDfmReport("not json")).toBeNull();
  });

  it("returns null when required fields are missing", () => {
    expect(parseDfmReport(JSON.stringify({ ok: true, parts: [] }))).toBeNull(); // no summary
    expect(parseDfmReport(JSON.stringify({ ok: true, summary: {} }))).toBeNull(); // no parts
  });
});

describe("DFM_SEVERITIES", () => {
  it("orders most-severe first", () => {
    expect(DFM_SEVERITIES).toEqual(["critical", "warning", "advisory"]);
  });
});
