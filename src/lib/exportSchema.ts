/**
 * Typed mirror of the engine export option schema (engine/solidifai_engine/
 * exports.py). The engine is the source of truth and validates everything; this
 * file lets the ExportDialog render the right controls and defaults without a
 * round trip. Keep field names and defaults in sync with exports.py.
 */

export type UnitKey = "micron" | "mm" | "cm" | "m" | "in" | "ft";
export type PrecisionKey = "average" | "greatest" | "least" | "session";
export type MeshTypeKey = "model" | "support" | "solid_support" | "other";
export type QualityKey = "draft" | "standard" | "fine" | "custom";

export type ExportOptions = Record<string, string | number | boolean>;

export interface FormatDef {
  key: string;
  label: string;
  ext: string;
  /** one-line descriptor (no em dashes) */
  blurb: string;
  /** BREP: exact, no options */
  exact?: boolean;
}

export const FORMATS: FormatDef[] = [
  { key: "step", label: "STEP", ext: "step", blurb: "CAD interchange, exact geometry." },
  { key: "stl", label: "STL", ext: "stl", blurb: "Mesh for 3D printing." },
  { key: "glb", label: "glTF / GLB", ext: "glb", blurb: "Web and realtime 3D." },
  { key: "brep", label: "BREP", ext: "brep", blurb: "Exact, perfect round-trip.", exact: true },
  { key: "3mf", label: "3MF", ext: "3mf", blurb: "Print format with metadata." },
];

export const UNIT_OPTIONS: { value: UnitKey; label: string }[] = [
  { value: "mm", label: "Millimeters (mm)" },
  { value: "micron", label: "Microns" },
  { value: "cm", label: "Centimeters" },
  { value: "m", label: "Meters" },
  { value: "in", label: "Inches" },
  { value: "ft", label: "Feet" },
];

export const PRECISION_OPTIONS: { value: PrecisionKey; label: string }[] = [
  { value: "average", label: "Average" },
  { value: "greatest", label: "Greatest" },
  { value: "least", label: "Least" },
  { value: "session", label: "Session" },
];

export const MESH_TYPE_OPTIONS: { value: MeshTypeKey; label: string }[] = [
  { value: "model", label: "Model" },
  { value: "support", label: "Support" },
  { value: "solid_support", label: "Solid support" },
  { value: "other", label: "Other" },
];

/** Quality preset to linear tolerance / deflection (mm), per format key. */
const QUALITY: Record<string, Record<Exclude<QualityKey, "custom">, number>> = {
  stl: { draft: 0.05, standard: 0.01, fine: 0.001 },
  glb: { draft: 0.01, standard: 0.001, fine: 0.0005 },
  gltf: { draft: 0.01, standard: 0.001, fine: 0.0005 },
  "3mf": { draft: 0.01, standard: 0.001, fine: 0.0005 },
};

export function qualityTolerance(formatKey: string, q: Exclude<QualityKey, "custom">): number {
  return QUALITY[formatKey][q];
}

/** The default options object for a format, matching exports.py defaults. */
export function defaultOptions(formatKey: string): ExportOptions {
  switch (formatKey) {
    case "step":
      return { unit: "mm", precision_mode: "average", write_pcurves: true, timestamp: "current" };
    case "stl":
      return { ascii: false, quality: "standard", tolerance: 0.01, angular_tolerance: 0.1 };
    case "glb":
    case "gltf":
      return { unit: "mm", quality: "standard", linear_deflection: 0.001, angular_deflection: 0.1 };
    case "brep":
      return {};
    case "3mf":
      return {
        unit: "mm",
        quality: "standard",
        linear_deflection: 0.001,
        angular_deflection: 0.1,
        mesh_type: "model",
        part_number: "",
        uuid: "",
      };
    default:
      return {};
  }
}
