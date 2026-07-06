/**
 * Design-requirements types + parser, mirroring the engine's `check_requirements`
 * (see `engine/solidifai_engine/requirements.py`). A requirement is a goal the
 * part must meet; the engine evaluates each against the live model.
 *
 * Predicate form: {id, quantity, op, bound, enabled}. Six built-in presets
 * desugar to predicates and double as quick-add chips in the composer.
 */

/* ── quantity + op vocabulary (mirrors engine registry) ── */

export type Quantity =
  | "mass"
  | "size"
  | "size_x"
  | "size_y"
  | "size_z"
  | "dfm_critical"
  | "overlaps"
  | "watertight"
  | "min_wall"
  | "min_clearance";

export type Op = "<=" | ">=" | "within" | "==";

/** How the bound input is rendered in the composer. */
export type TargetKind = "scalar" | "range" | "vector" | "none";

export interface QuantityMeta {
  quantity: Quantity;
  label: string;
  unit: string | null;
  targetKind: TargetKind;
}

export const QUANTITIES: QuantityMeta[] = [
  { quantity: "mass", label: "Mass", unit: "g", targetKind: "scalar" },
  { quantity: "size", label: "Fits in box", unit: "mm", targetKind: "vector" },
  { quantity: "size_x", label: "Size X", unit: "mm", targetKind: "scalar" },
  { quantity: "size_y", label: "Size Y", unit: "mm", targetKind: "scalar" },
  { quantity: "size_z", label: "Size Z", unit: "mm", targetKind: "scalar" },
  { quantity: "dfm_critical", label: "Critical DFM issues", unit: null, targetKind: "none" },
  { quantity: "overlaps", label: "Overlapping parts", unit: null, targetKind: "none" },
  { quantity: "watertight", label: "Watertight", unit: null, targetKind: "none" },
  { quantity: "min_wall", label: "Min wall thickness", unit: "mm", targetKind: "scalar" },
  { quantity: "min_clearance", label: "Min clearance", unit: "mm", targetKind: "scalar" },
];

export const OPS: { op: Op; label: string }[] = [
  { op: "<=", label: "at most" },
  { op: ">=", label: "at least" },
  { op: "within", label: "between" },
  { op: "==", label: "equals" },
];

/* ── requirement (predicate form) ── */

/** Scalar or boolean bound for simple predicates. */
export type ScalarBound = number | boolean;
/** Two-value bound for `within` op. */
export type RangeBound = [number, number];
/** Per-axis bound for `size` quantity. */
export type VectorBound = [number, number, number];
export type Bound = ScalarBound | RangeBound | VectorBound;

/** Predicate requirement: the engine-canonical form. */
export interface PredicateRequirement {
  id: string;
  quantity: Quantity;
  op: Op;
  bound: Bound;
  label?: string;
  enabled?: boolean;
}

/** Assert requirement (escape hatch; lowTrust, engine-side expression eval). */
export interface AssertRequirement {
  id: string;
  kind: "assert";
  expr: string;
  label?: string;
  enabled?: boolean;
}

export type Requirement = PredicateRequirement | AssertRequirement;

export function isAssert(r: Requirement): r is AssertRequirement {
  return (r as AssertRequirement).kind === "assert";
}

/* ── result rows ── */

export type Delta = "unchanged" | "regressed" | "fixed" | "new";

export interface RequirementResult {
  id: string;
  /** Present for predicate rows. */
  quantity?: Quantity;
  op?: Op;
  bound?: Bound;
  /** Present for assert rows. */
  kind?: "assert";
  label: string;
  measured: number | number[] | boolean | null;
  unit: string | null;
  pass: boolean | null;
  detail: string;
  /** Regression tracking vs the previous build. */
  delta?: Delta;
  /** Assert rows set this; indicates lower confidence in the result. */
  lowTrust?: boolean;
}

export interface RequirementsReport {
  ok: true;
  schema: 1;
  buildId: number;
  requirements: RequirementResult[];
  summary: {
    met: number;
    total: number;
    allMet: boolean;
    /** Count of newly broken goals since the previous build. */
    regressed?: number;
    /** Count of newly fixed goals since the previous build. */
    fixed?: number;
  };
}

/* ── converge result ── */

export interface ConvergeResult {
  ok: boolean;
  found: boolean;
  buildIdBefore: number;
  evaluated: number;
  objective: string;
  /** Proposed parameter values, or null when not found. */
  params: Record<string, number> | null;
  before: RequirementResult[];
  after: RequirementResult[] | null;
  /** The best candidate when no fully feasible one was found. */
  closestMiss?: Record<string, unknown> | null;
  notAddressable: { id: string; label: string }[];
  error?: string;
}

/* ── six preset chips (quick-add) ── */

/** Legacy type string used by preset definitions. */
export type PresetType =
  "max_mass" | "min_mass" | "max_size" | "printable" | "no_interference" | "watertight";

export interface PresetMeta {
  type: PresetType;
  label: string;
  /** A default bound so one tap adds a sensible goal. */
  defaultBound: Bound;
}

export const PRESETS: PresetMeta[] = [
  { type: "max_mass", label: "Max mass", defaultBound: 50 },
  { type: "min_mass", label: "Min mass", defaultBound: 10 },
  { type: "max_size", label: "Fits in box", defaultBound: [60, 40, 20] },
  { type: "printable", label: "Printable (FDM)", defaultBound: 0 },
  { type: "no_interference", label: "No interference", defaultBound: 0 },
  { type: "watertight", label: "Watertight", defaultBound: true },
];

/** Desugar a preset type into a predicate requirement. */
export function presetToRequirement(type: PresetType, bound?: Bound): PredicateRequirement {
  switch (type) {
    case "max_mass":
      return {
        id: crypto.randomUUID(),
        quantity: "mass",
        op: "<=",
        bound: (bound ?? 50) as number,
        enabled: true,
      };
    case "min_mass":
      return {
        id: crypto.randomUUID(),
        quantity: "mass",
        op: ">=",
        bound: (bound ?? 10) as number,
        enabled: true,
      };
    case "max_size":
      return {
        id: crypto.randomUUID(),
        quantity: "size",
        op: "<=",
        bound: (bound ?? [60, 40, 20]) as VectorBound,
        enabled: true,
      };
    case "printable":
      return {
        id: crypto.randomUUID(),
        quantity: "dfm_critical",
        op: "<=",
        bound: 0,
        label: "Printable (FDM)",
        enabled: true,
      };
    case "no_interference":
      return {
        id: crypto.randomUUID(),
        quantity: "overlaps",
        op: "<=",
        bound: 0,
        label: "No interference",
        enabled: true,
      };
    case "watertight":
      return {
        id: crypto.randomUUID(),
        quantity: "watertight",
        op: "==",
        bound: true,
        enabled: true,
      };
  }
}

/* ── parse helpers ── */

/** Re-derive an editable predicate requirement from an evaluated result row. */
export function toRequirement(r: RequirementResult): Requirement {
  if (r.kind === "assert") {
    // Assert rows can't be roundtripped to full AssertRequirement without `expr`
    // so return a minimal identity placeholder the editor won't persist.
    return { id: r.id, kind: "assert", expr: "", label: r.label, enabled: true };
  }
  if (r.quantity && r.op && r.bound !== undefined) {
    return {
      id: r.id,
      quantity: r.quantity,
      op: r.op,
      bound: r.bound,
      label: r.label,
      enabled: true,
    };
  }
  // Fallback: treat as a max_mass predicate (should not occur with engine schema 1).
  return {
    id: r.id,
    quantity: "mass",
    op: "<=",
    bound: 0,
    enabled: true,
  };
}

export function parseRequirementsReport(raw: string): RequirementsReport | null {
  try {
    const v = JSON.parse(raw) as Record<string, unknown>;
    if (v && v.ok === true && Array.isArray(v.requirements) && typeof v.summary === "object") {
      return v as unknown as RequirementsReport;
    }
    return null;
  } catch {
    return null;
  }
}

export function parseConvergeResult(raw: string): ConvergeResult | null {
  try {
    const v = JSON.parse(raw) as Record<string, unknown>;
    if (v && typeof v.ok === "boolean" && typeof v.found === "boolean") {
      return v as unknown as ConvergeResult;
    }
    return null;
  } catch {
    return null;
  }
}

/* ── legacy compat (kept so existing callers compile) ── */

/** @deprecated Use Quantity instead. */
export type RequirementType = PresetType;

/** @deprecated Use PRESETS instead. */
export interface RequirementTypeMeta {
  type: PresetType;
  label: string;
  targetKind: "mass" | "size" | "none";
  defaultTarget: number | [number, number, number] | null;
}

/** @deprecated Use PRESETS instead. */
export const REQUIREMENT_TYPES: RequirementTypeMeta[] = [
  { type: "max_mass", label: "Max mass", targetKind: "mass", defaultTarget: 50 },
  { type: "min_mass", label: "Min mass", targetKind: "mass", defaultTarget: 10 },
  { type: "max_size", label: "Fits in box", targetKind: "size", defaultTarget: [60, 40, 20] },
  { type: "printable", label: "Printable (FDM)", targetKind: "none", defaultTarget: null },
  { type: "no_interference", label: "No interference", targetKind: "none", defaultTarget: null },
  { type: "watertight", label: "Watertight", targetKind: "none", defaultTarget: null },
];
