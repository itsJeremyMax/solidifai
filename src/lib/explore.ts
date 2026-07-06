/**
 * Generative-exploration types + parsers, mirroring the engine's `sweep` /
 * `optimize` (see `engine/solidifai_engine/explore.py` + Session). All
 * non-destructive: the live model is never changed by exploring.
 */

export type Objective = "min_mass" | "max_mass";

export interface SweepVariant {
  value: number;
  ok: boolean;
  mass?: number;
  volume?: number;
  bbox?: [number, number, number];
  dfmCritical?: number;
  error?: string;
}

export interface SweepReport {
  ok: true;
  param: string;
  unit: string | null;
  variants: SweepVariant[];
}

export interface OptimizeResult {
  ok: true;
  param: string;
  objective: Objective;
  best: SweepVariant | null;
  feasibleCount: number;
  evaluated: SweepVariant[];
}

export function parseSweepReport(raw: string): SweepReport | null {
  try {
    const v = JSON.parse(raw) as Record<string, unknown>;
    if (v && v.ok === true && Array.isArray(v.variants)) return v as unknown as SweepReport;
    return null;
  } catch {
    return null;
  }
}

export function parseOptimizeResult(raw: string): OptimizeResult | null {
  try {
    const v = JSON.parse(raw) as Record<string, unknown>;
    if (v && v.ok === true && Array.isArray(v.evaluated)) return v as unknown as OptimizeResult;
    return null;
  } catch {
    return null;
  }
}
