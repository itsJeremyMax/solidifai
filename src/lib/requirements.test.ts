import { describe, it, expect } from "vitest";

import {
  parseRequirementsReport,
  parseConvergeResult,
  toRequirement,
  presetToRequirement,
  PRESETS,
  type RequirementResult,
  type PredicateRequirement,
} from "./requirements";

/* ── parseRequirementsReport ─────────────────────────────────────────────── */

describe("parseRequirementsReport", () => {
  it("accepts a well-formed predicate-form report with delta", () => {
    const raw = JSON.stringify({
      ok: true,
      schema: 1,
      buildId: 4,
      requirements: [
        {
          id: "m",
          quantity: "mass",
          op: "<=",
          bound: 50,
          label: "Under 50 g",
          measured: 42,
          unit: "g",
          pass: true,
          detail: "",
          delta: "unchanged",
        },
      ],
      summary: { met: 1, total: 1, allMet: true, regressed: 0, fixed: 0 },
    });
    const r = parseRequirementsReport(raw);
    expect(r?.summary.allMet).toBe(true);
    expect(r?.summary.regressed).toBe(0);
    expect(r?.requirements[0].pass).toBe(true);
    expect(r?.requirements[0].delta).toBe("unchanged");
    expect(r?.requirements[0].quantity).toBe("mass");
  });

  it("accepts a report without delta (engine not yet updated)", () => {
    const raw = JSON.stringify({
      ok: true,
      schema: 1,
      buildId: 5,
      requirements: [
        {
          id: "s",
          quantity: "watertight",
          op: "==",
          bound: true,
          label: "Watertight",
          measured: true,
          unit: null,
          pass: true,
          detail: "",
        },
      ],
      summary: { met: 1, total: 1, allMet: true },
    });
    const r = parseRequirementsReport(raw);
    expect(r?.requirements[0].delta).toBeUndefined();
  });

  it("rejects an error envelope and garbage", () => {
    expect(parseRequirementsReport(JSON.stringify({ ok: false }))).toBeNull();
    expect(parseRequirementsReport("nope")).toBeNull();
  });

  it("threads delta values through summary", () => {
    const raw = JSON.stringify({
      ok: true,
      schema: 1,
      buildId: 10,
      requirements: [],
      summary: { met: 0, total: 0, allMet: true, regressed: 2, fixed: 1 },
    });
    const r = parseRequirementsReport(raw);
    expect(r?.summary.regressed).toBe(2);
    expect(r?.summary.fixed).toBe(1);
  });
});

/* ── toRequirement ────────────────────────────────────────────────────────── */

describe("toRequirement", () => {
  it("derives a predicate requirement from a predicate result row", () => {
    const row: RequirementResult = {
      id: "z",
      quantity: "size",
      op: "<=",
      bound: [60, 40, 20],
      label: "Fits",
      measured: [10, 10, 10],
      unit: "mm",
      pass: true,
      detail: "",
      delta: "unchanged",
    };
    const req = toRequirement(row) as PredicateRequirement;
    expect(req.id).toBe("z");
    expect(req.quantity).toBe("size");
    expect(req.op).toBe("<=");
    expect(req.bound).toEqual([60, 40, 20]);
    expect(req.enabled).toBe(true);
  });

  it("handles assert rows gracefully", () => {
    const row: RequirementResult = {
      id: "a",
      kind: "assert",
      label: "custom",
      measured: null,
      unit: null,
      pass: null,
      detail: "",
    };
    const req = toRequirement(row);
    expect((req as { kind: string }).kind).toBe("assert");
    expect(req.id).toBe("a");
  });
});

/* ── preset → predicate desugaring ──────────────────────────────────────── */

describe("presetToRequirement", () => {
  it("max_mass desugars to mass <= bound", () => {
    const r = presetToRequirement("max_mass", 80);
    expect(r.quantity).toBe("mass");
    expect(r.op).toBe("<=");
    expect(r.bound).toBe(80);
    expect(r.enabled).toBe(true);
  });

  it("min_mass desugars to mass >= default", () => {
    const r = presetToRequirement("min_mass");
    expect(r.quantity).toBe("mass");
    expect(r.op).toBe(">=");
    expect(r.bound).toBe(10);
  });

  it("max_size desugars to size <= [x,y,z]", () => {
    const r = presetToRequirement("max_size", [100, 80, 60]);
    expect(r.quantity).toBe("size");
    expect(r.op).toBe("<=");
    expect(r.bound).toEqual([100, 80, 60]);
  });

  it("max_size uses default bound when none provided", () => {
    const r = presetToRequirement("max_size");
    expect(r.bound).toEqual([60, 40, 20]);
  });

  it("printable desugars to dfm_critical <= 0", () => {
    const r = presetToRequirement("printable");
    expect(r.quantity).toBe("dfm_critical");
    expect(r.op).toBe("<=");
    expect(r.bound).toBe(0);
  });

  it("no_interference desugars to overlaps <= 0", () => {
    const r = presetToRequirement("no_interference");
    expect(r.quantity).toBe("overlaps");
    expect(r.op).toBe("<=");
    expect(r.bound).toBe(0);
  });

  it("watertight desugars to watertight == true", () => {
    const r = presetToRequirement("watertight");
    expect(r.quantity).toBe("watertight");
    expect(r.op).toBe("==");
    expect(r.bound).toBe(true);
  });

  it("all six presets produce a non-empty id", () => {
    for (const p of PRESETS) {
      const r = presetToRequirement(p.type);
      expect(r.id.length).toBeGreaterThan(0);
    }
  });

  it("each preset produces a unique id per call", () => {
    const a = presetToRequirement("max_mass");
    const b = presetToRequirement("max_mass");
    expect(a.id).not.toBe(b.id);
  });
});

/* ── parseConvergeResult ─────────────────────────────────────────────────── */

describe("parseConvergeResult", () => {
  it("parses a found result", () => {
    const raw = JSON.stringify({
      ok: true,
      found: true,
      buildIdBefore: 7,
      evaluated: 12,
      objective: "min_mass",
      params: { wall: 1.5 },
      before: [],
      after: [],
      closestMiss: null,
      notAddressable: [],
    });
    const r = parseConvergeResult(raw);
    expect(r?.found).toBe(true);
    expect(r?.params).toEqual({ wall: 1.5 });
    expect(r?.evaluated).toBe(12);
  });

  it("parses a not-found result with closestMiss", () => {
    const raw = JSON.stringify({
      ok: true,
      found: false,
      buildIdBefore: 3,
      evaluated: 8,
      objective: "min_mass",
      params: null,
      before: [],
      after: null,
      closestMiss: { wall: 1.0, min_wall: 0.9 },
      notAddressable: [{ id: "w", label: "Watertight" }],
    });
    const r = parseConvergeResult(raw);
    expect(r?.found).toBe(false);
    expect(r?.params).toBeNull();
    expect(r?.notAddressable).toHaveLength(1);
  });

  it("returns null for invalid input", () => {
    expect(parseConvergeResult("garbage")).toBeNull();
    expect(parseConvergeResult(JSON.stringify({ ok: true }))).toBeNull();
  });
});

/* ── result-row parsing with delta ──────────────────────────────────────── */

describe("result row delta values", () => {
  const makeReport = (delta: string) =>
    JSON.stringify({
      ok: true,
      schema: 1,
      buildId: 1,
      requirements: [
        {
          id: "x",
          quantity: "mass",
          op: "<=",
          bound: 50,
          label: "test",
          measured: 45,
          unit: "g",
          pass: true,
          detail: "",
          delta,
        },
      ],
      summary: { met: 1, total: 1, allMet: true },
    });

  it.each(["unchanged", "regressed", "fixed", "new"] as const)("round-trips delta=%s", (delta) => {
    const r = parseRequirementsReport(makeReport(delta));
    expect(r?.requirements[0].delta).toBe(delta);
  });
});
