/** The engine-owned, versioned export catalog. */
import catalog from "../../engine/solidifai_engine/export_schema.json";

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

type CatalogFormat = {
  label: string;
  ext: string;
  blurb: string;
  exact?: boolean;
  fields: Record<string, { default: string | number | boolean }>;
  quality?: Record<Exclude<QualityKey, "custom">, number>;
};

const formats = catalog.formats as Record<string, CatalogFormat>;

export const FORMATS: FormatDef[] = Object.entries(formats).map(([key, format]) => ({
  key,
  label: format.label,
  ext: format.ext,
  blurb: format.blurb,
  exact: format.exact,
}));

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

export function qualityTolerance(formatKey: string, q: Exclude<QualityKey, "custom">): number {
  return formats[formatKey].quality![q];
}

/** The default options object for a format, matching exports.py defaults. */
export function defaultOptions(formatKey: string): ExportOptions {
  const format = formats[formatKey];
  return format
    ? Object.fromEntries(Object.entries(format.fields).map(([key, field]) => [key, field.default]))
    : {};
}
