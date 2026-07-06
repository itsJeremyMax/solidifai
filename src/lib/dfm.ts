/**
 * DFM (design-for-manufacturing) report types + parser.
 *
 * Mirrors the engine's `analyze_dfm` response (see
 * `engine/solidifai_engine/dfm.py` + `Session.analyze_dfm`). The report is
 * advisory: each violation carries its severity, the measured value vs the
 * threshold, a representative location, and the source of the rule.
 */

export type DfmSeverity = "critical" | "warning" | "advisory";

export type DfmRule = "wall_thickness" | "overhang" | "bridge" | "small_hole";

export interface DfmViolation {
  rule: DfmRule;
  severity: DfmSeverity;
  message: string;
  measured: { value: number; unit: string };
  threshold: { value: number; unit: string };
  location: [number, number, number] | null;
  source: string;
  /** wall-thickness findings are sampled (advisory, not a proof). */
  sampled?: boolean;
  /** The measured minimum wall (mm) across the part, present on wall_thickness findings. */
  minWall?: { value: number; unit: string };
  /**
   * A wall finding from an isolated thin reading on a curved or edge region: the
   * thickness is ill-defined there, so it is surfaced as a possible sampling
   * artifact rather than a hard violation.
   */
  possibleArtifact?: boolean;
  /** Local geometry of a wall finding (originating face type, curvature, region size). */
  classification?: {
    faceType: string;
    curved: boolean;
    areaMm2: number;
    samples: number;
  };
  hint: string;
}

export interface DfmPartMetrics {
  /** Measured minimum wall thickness (mm) across the part, or null when unsampled. */
  minWallMm: number | null;
}

export interface DfmPart {
  /** Slug node id — matches `model.json` object ids, so it drives selection. */
  partId: string;
  partName: string;
  process: string;
  evaluated: boolean;
  violations: DfmViolation[];
  /** Measured geometry numbers that always hold, even with no violation (e.g. min wall). */
  metrics?: DfmPartMetrics;
  /** Present only when `evaluated` is false (e.g. a process the DFM engine does not yet support). */
  note?: string;
}

export interface DfmSummary {
  critical: number;
  warning: number;
  advisory: number;
  parts: number;
  /** Thinnest measured wall (mm) across all evaluated parts, or null. */
  minWallMm?: number | null;
}

export interface DfmReport {
  ok: true;
  schema: 1;
  buildId: number;
  parts: DfmPart[];
  summary: DfmSummary;
}

/** Severity render order: most severe first. */
export const DFM_SEVERITIES: DfmSeverity[] = ["critical", "warning", "advisory"];

/**
 * Parse the raw engine response into a `DfmReport`, or `null` when the engine
 * returned an error envelope / unparseable text. Defensive: never throws.
 */
export function parseDfmReport(raw: string): DfmReport | null {
  try {
    const v = JSON.parse(raw) as Record<string, unknown>;
    if (v && v.ok === true && Array.isArray(v.parts) && typeof v.summary === "object") {
      return v as unknown as DfmReport;
    }
    return null;
  } catch {
    return null;
  }
}
