import { describe, expect, it } from "vitest";

import { parseEstimate, parseInstallInfo, parseOrientResult } from "./fabrication";

/* ── InstallInfo ─────────────────────────────────────────────────────────── */

describe("parseInstallInfo", () => {
  it("parses a found slicer", () => {
    const raw = JSON.stringify({
      found: true,
      version: "1.9.0",
      executable: "/Applications/OrcaSlicer.app/Contents/MacOS/OrcaSlicer",
    });
    const info = parseInstallInfo(raw);
    expect(info).not.toBeNull();
    expect(info!.found).toBe(true);
    expect(info!.version).toBe("1.9.0");
  });

  it("parses a not-found result", () => {
    const raw = JSON.stringify({ found: false });
    const info = parseInstallInfo(raw);
    expect(info).not.toBeNull();
    expect(info!.found).toBe(false);
    expect(info!.version).toBeUndefined();
    expect(info!.executable).toBeUndefined();
  });

  it("returns null for invalid json", () => {
    expect(parseInstallInfo("not json")).toBeNull();
  });

  it("returns null when found field is missing", () => {
    expect(parseInstallInfo(JSON.stringify({ version: "1.0" }))).toBeNull();
  });
});

/* ── Estimate — slice source ─────────────────────────────────────────────── */

describe("parseEstimate — slice source", () => {
  it("parses a full slice estimate (real engine envelope)", () => {
    // Matches the actual fab_estimate response: fields nested under `estimate`.
    const raw = JSON.stringify({
      ok: true,
      source: "slice",
      estimate: {
        source: "slice",
        timeSeconds: 15120,
        filamentGrams: 38.4,
        filamentLengthMm: 12880,
        cost: 1.15,
        currency: "USD",
      },
    });
    const est = parseEstimate(raw);
    expect(est).not.toBeNull();
    expect(est!.source).toBe("slice");
    expect(est!.timeSeconds).toBe(15120);
    expect(est!.filamentGrams).toBe(38.4);
    expect(est!.filamentLengthMm).toBe(12880);
    expect(est!.cost).toBe(1.15);
    expect(est!.currency).toBe("USD");
    expect(est!.note).toBeUndefined();
  });
});

/* ── Estimate — approx source ────────────────────────────────────────────── */

describe("parseEstimate — approx source", () => {
  it("parses an approx estimate (real engine envelope, no time)", () => {
    // Matches the actual fab_estimate response for the approx path.
    const raw = JSON.stringify({
      ok: true,
      source: "approx",
      estimate: {
        source: "approx",
        filamentGrams: 12.5,
        cost: 0.38,
        currency: "USD",
        timeSeconds: null,
        note: "approximate; install OrcaSlicer for print time and exact filament",
      },
    });
    const est = parseEstimate(raw);
    expect(est).not.toBeNull();
    expect(est!.source).toBe("approx");
    // timeSeconds:null comes through as null, not undefined — treat either as falsy.
    expect(est!.timeSeconds ?? undefined).toBeUndefined();
    expect(est!.filamentGrams).toBe(12.5);
    expect(est!.cost).toBe(0.38);
    expect(est!.currency).toBe("USD");
    expect(est!.note).toContain("approximate");
  });

  it("returns null for ok:false (no model loaded)", () => {
    // Engine returns this when no geometry is present.
    const raw = JSON.stringify({ ok: false, error: "no model loaded" });
    expect(parseEstimate(raw)).toBeNull();
  });

  it("returns null when inner estimate is missing source", () => {
    expect(parseEstimate(JSON.stringify({ ok: true, estimate: { currency: "USD" } }))).toBeNull();
  });

  it("returns null for unparseable input", () => {
    expect(parseEstimate("{bad}")).toBeNull();
  });
});

it("parses the richer slice estimate fields", () => {
  const raw = JSON.stringify({
    estimate: {
      source: "slice",
      currency: "USD",
      timeSeconds: 1685,
      filamentGrams: 3.95,
      layerCount: 100,
      supportUsed: false,
      heightMm: 20,
      fitsBed: true,
      cost: 0.0987,
    },
  });
  const est = parseEstimate(raw);
  expect(est?.layerCount).toBe(100);
  expect(est?.fitsBed).toBe(true);
  expect(est?.supportUsed).toBe(false);
  expect(est?.heightMm).toBe(20);
});

/* ── OrientResult ────────────────────────────────────────────────────────── */

describe("parseOrientResult", () => {
  it("parses a valid orient result", () => {
    const raw = JSON.stringify({
      rotation: [0.0, 0.0, 90.0],
      supportArea: 120.5,
      contactArea: 450.0,
      worstSupportArea: 980.0,
    });
    const result = parseOrientResult(raw);
    expect(result).not.toBeNull();
    expect(result!.rotation).toEqual([0.0, 0.0, 90.0]);
    expect(result!.supportArea).toBe(120.5);
    expect(result!.worstSupportArea).toBe(980.0);
  });

  it("parses identity orientation (flat on bed)", () => {
    const raw = JSON.stringify({
      rotation: [0, 0, 0],
      supportArea: 0,
      contactArea: 1600.0,
      worstSupportArea: 200.0,
    });
    const result = parseOrientResult(raw);
    expect(result).not.toBeNull();
    expect(result!.rotation).toEqual([0, 0, 0]);
    expect(result!.supportArea).toBe(0);
  });

  it("returns null when rotation is absent", () => {
    expect(
      parseOrientResult(JSON.stringify({ supportArea: 0, contactArea: 0, worstSupportArea: 0 })),
    ).toBeNull();
  });

  it("returns null for malformed json", () => {
    expect(parseOrientResult("bad")).toBeNull();
  });
});
