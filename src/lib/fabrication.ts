/**
 * Fabrication types + parse helpers, mirroring the engine's fab_* RPC methods.
 *
 * All parse functions accept the raw JSON string from ipc and return a typed
 * object on success, or null on bad/empty input.
 */

/** Installed-slicer detection result from `fab_detect`. */
export interface InstallInfo {
  found: boolean;
  version?: string;
  executable?: string;
}

/** Print-time / material estimate from `fab_estimate`. */
export interface Estimate {
  source: string;
  timeSeconds?: number;
  filamentGrams?: number;
  filamentLengthMm?: number;
  cost?: number;
  currency: string;
  note?: string;
  layerCount?: number;
  supportUsed?: boolean;
  heightMm?: number;
  fitsBed?: boolean;
}

/** Best-orientation result from `fab_orient`. */
export interface OrientResult {
  rotation: [number, number, number];
  supportArea: number;
  contactArea: number;
  worstSupportArea: number;
}

/** One configured print / export destination from `list_destinations`. */
export interface Destination {
  id: string;
  name: string;
  kind: string;
  provider: string;
  printerProfile?: string;
  filamentProfile?: string;
  processProfile?: string;
  connection?: string;
}

/** Slicer status + profile catalogue from the native `get_slicer_profiles`. */
export interface ProfileSet {
  /** True when an OrcaSlicer executable was found on this machine. */
  found: boolean;
  /** Detected slicer version (e.g. "2.1.1"), when the probe succeeded. */
  version?: string;
  printers: string[];
  filaments: string[];
  processes: string[];
}

/** One supported slicer in Settings → Slicers (`get_slicer_config`). */
export interface SlicerEntry {
  id: string;
  label: string;
  found: boolean;
  /** Resolved executable in use (override or auto-detected). */
  executable?: string;
  version?: string;
  /** User-set override path; absent means "auto-detect". */
  overridePath?: string;
}

export function parseInstallInfo(raw: string): InstallInfo | null {
  try {
    const v = JSON.parse(raw) as Record<string, unknown>;
    if (v && typeof v.found === "boolean") return v as unknown as InstallInfo;
    return null;
  } catch {
    return null;
  }
}

export function parseEstimate(raw: string): Estimate | null {
  try {
    const v = JSON.parse(raw) as Record<string, unknown>;
    if (!v || typeof v !== "object") return null;
    // Engine wraps the estimate fields under v.estimate; fall back to flat shape
    // for test fixtures or future envelope changes.
    const inner =
      v.estimate && typeof v.estimate === "object" ? (v.estimate as Record<string, unknown>) : v;
    if (typeof inner.source === "string" && typeof inner.currency === "string") {
      return inner as unknown as Estimate;
    }
    return null;
  } catch {
    return null;
  }
}

export function parseOrientResult(raw: string): OrientResult | null {
  try {
    const v = JSON.parse(raw) as Record<string, unknown>;
    if (v && Array.isArray(v.rotation) && typeof v.supportArea === "number") {
      return v as unknown as OrientResult;
    }
    return null;
  } catch {
    return null;
  }
}
