/**
 * Validation report types + parsers.
 *
 * Mirrors the engine's `measure`, `stress_check`, and `tolerance_stack`
 * responses (see `engine/solidifai_engine/props.py`, `validation.py`, and the
 * matching `Session` methods). All advisory and read-only: nothing here mutates
 * the model.
 */

// --- mass properties (measure) ----------------------------------------------

export interface Inertia {
  frame: "centerOfMass";
  /** g·mm², about the center of mass, in model X/Y/Z. */
  tensor: [number, number, number][];
  /** Ascending principal moments (g·mm²). */
  principalMoments: number[];
  /** Orthonormal principal axes (rows), aligned with principalMoments. */
  principalAxes: number[][];
}

export interface MassProperties {
  volume: number; // mm³
  surfaceArea: number; // mm²
  mass: number; // g
  density: number; // g/cm³
  centerOfMass: [number, number, number];
  bbox: { size: number[]; min: number[]; max: number[] };
  inertia: Inertia;
  valid: boolean;
  manifold: boolean;
}

export interface MeasurePart extends Partial<MassProperties> {
  partId: string;
  partName: string;
  material?: string;
  /** Reference imports are listed but carry no mass properties. */
  role?: "reference";
}

export interface AssemblyTotal {
  mass: number;
  volume: number;
  centerOfMass: [number, number, number];
  inertia: Inertia | null;
}

export interface MeasureReport {
  ok: true;
  schema: 1;
  buildId: number;
  parts: MeasurePart[];
  total: AssemblyTotal;
  summary: { parts: number; mass: number; unit: "g" };
}

/** A measured part that actually has geometry (not a reference). */
export function isSolidPart(p: MeasurePart): p is MeasurePart & MassProperties {
  return p.role !== "reference" && typeof p.mass === "number";
}

export function parseMeasureReport(raw: string): MeasureReport | null {
  try {
    const v = JSON.parse(raw) as Record<string, unknown>;
    if (v && v.ok === true && Array.isArray(v.parts) && typeof v.total === "object") {
      return v as unknown as MeasureReport;
    }
    return null;
  } catch {
    return null;
  }
}

// --- stress hot-spots --------------------------------------------------------

export type StressSeverity = "warning" | "advisory";

export interface StressHotspot {
  rule: "sharp_internal_corner";
  severity: StressSeverity;
  message: string;
  measured: { value: number; unit: string };
  threshold: { value: number; unit: string };
  location: [number, number, number] | null;
  source: string;
  hint: string;
}

export interface StressPart {
  partId: string;
  partName: string;
  hotspots: StressHotspot[];
}

export interface StressReport {
  ok: true;
  schema: 1;
  buildId: number;
  parts: StressPart[];
  summary: { warning: number; advisory: number; parts: number };
}

/** Severity render order: most severe first. */
export const STRESS_SEVERITIES: StressSeverity[] = ["warning", "advisory"];

export function parseStressReport(raw: string): StressReport | null {
  try {
    const v = JSON.parse(raw) as Record<string, unknown>;
    if (v && v.ok === true && Array.isArray(v.parts) && typeof v.summary === "object") {
      return v as unknown as StressReport;
    }
    return null;
  } catch {
    return null;
  }
}

// --- tolerance stack ---------------------------------------------------------

export type FitType = "clearance" | "transition" | "interference";

export interface ToleranceLink {
  label?: string;
  nominal: number;
  plus: number;
  minus: number;
  direction?: number;
  resolvedFrom?: string;
}

export interface ToleranceResult {
  ok: true;
  nominal: number;
  worstCase: { min: number; max: number; range: number };
  rss: { min: number; max: number; range: number };
  fit?: { type: FitType; minGap: number; maxGap: number };
  links: ToleranceLink[];
}

export function parseToleranceResult(raw: string): ToleranceResult | null {
  try {
    const v = JSON.parse(raw) as Record<string, unknown>;
    if (v && v.ok === true && typeof v.worstCase === "object") {
      return v as unknown as ToleranceResult;
    }
    return null;
  } catch {
    return null;
  }
}
