/**
 * Artifact types + parsing for the engine's `model.json` render manifest.
 *
 * The engine writes a `model.json` (this {@link ModelInfo} shape) plus a sibling
 * `model.glb` on every successful build. The Rust side surfaces one immutable
 * generation through `read_model_snapshot`; a `model-updated` event carries its
 * `publicationId` and `buildId` whenever a fresh build lands. {@link parseModelInfo}
 * validates the JSON defensively so a malformed manifest degrades to `null` rather
 * than throwing into the render path.
 */

/** Per-object PBR appearance resolved by the engine (schema 2+). */
export interface Appearance {
  /** Canonical material id, e.g. "aluminum". Informational. */
  material: string;
  /** Linear RGB base color, 0..1. */
  baseColor: Vec3;
  metalness: number;
  roughness: number;
  clearcoat: number;
  clearcoatRoughness: number;
  /** Render opacity 0..1 (schema 2+). < 1 ghosts the object (imported references). */
  opacity?: number;
}

/**
 * A single solid/feature in the build. Joined to GLB meshes by ORDER (the i-th
 * object ↔ the i-th child mesh), not by `node` name — build123d's glTF export
 * does not preserve readable node names.
 */
export interface ModelObject {
  id: string;
  name: string;
  kind: string;
  /** Engine-side node slug; NOT a reliable GLB scene-graph key (see above). */
  node: string;
  visible: boolean;
  /** "part" = your designed geometry; "reference" = a ghosted imported fixture
   *  you fit around (not exported, not DFM'd). Defaults to "part" when absent. */
  role?: "part" | "reference";
  /** Present in schema 2+. Absent for legacy schema-1 history artifacts. */
  appearance?: Appearance;
  /** Per-object mass (schema 2+). Null for references (no manufactured mass). */
  mass?: { value: number; material: string; density: number } | null;
  /** Exact occurrence identity, present ONLY on a repeated/mirrored placement
   *  body (the 2nd, 3rd ... placement of an instanced part or sub-assembly): the
   *  id of its first-placement counterpart. Absent on ordinary bodies and on the
   *  primary placement, so its presence anywhere in a payload signals a
   *  field-aware engine. Lets the tree/viewport group instances exactly instead
   *  of guessing from a `_N` slug. */
  occurrenceOf?: string;
  /** Placement number (2, 3, ...) of an occurrence body; pairs with
   *  {@link occurrenceOf}. */
  occurrenceIndex?: number;
}

/** A `[x, y, z]` triple in model units (mm). */
export type Vec3 = [number, number, number];

/** Definition for one numeric tunable parameter (slider bounds + unit + description). */
export interface ParamNumberSchemaEntry {
  type?: string;
  value: number;
  min: number;
  max: number;
  step: number;
  unit: string;
  /** Short, plain-language description ("" when none). Rendered as a subtitle. */
  desc: string;
}

export interface ParamBooleanSchemaEntry {
  type: "boolean";
  value: boolean;
  desc: string;
}

export interface ParamEnumSchemaEntry {
  type: "enum";
  value: string;
  choices: string[];
  desc: string;
}

export type NumericParamSchemaEntry = ParamNumberSchemaEntry;

export type ParamSchemaEntry =
  ParamNumberSchemaEntry | ParamBooleanSchemaEntry | ParamEnumSchemaEntry;

export type ParamValue = number | boolean | string;

/** The full render manifest emitted alongside `model.glb`. */
export interface ModelInfo {
  schema: 1 | 2;
  buildId: number;
  units: "mm";
  build: { ok: boolean; durationMs: number; warnings: string[] };
  objects: ModelObject[];
  bbox: { size: Vec3; min: Vec3; max: Vec3 } | null;
  volume: number;
  centerOfMass: Vec3 | null;
  mass: { value: number; material: string; density: number };
  valid: boolean;
  manifold: boolean;
  params: {
    schema: Record<string, ParamSchemaEntry>;
    values: Record<string, ParamValue>;
  };
}

function isVec3(v: unknown): v is Vec3 {
  return (
    Array.isArray(v) &&
    v.length === 3 &&
    v.every((n) => typeof n === "number" && Number.isFinite(n))
  );
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function isModelObject(v: unknown): v is ModelObject {
  if (!isRecord(v)) return false;
  return (
    typeof v.id === "string" &&
    typeof v.name === "string" &&
    typeof v.kind === "string" &&
    typeof v.node === "string" &&
    typeof v.visible === "boolean"
  );
}

export function isNumericParamSchemaEntry(v: ParamSchemaEntry): v is NumericParamSchemaEntry {
  return typeof v.value === "number" && "min" in v && "max" in v && "step" in v;
}

export function isBooleanParamSchemaEntry(v: ParamSchemaEntry): v is ParamBooleanSchemaEntry {
  return "type" in v && v.type === "boolean" && typeof v.value === "boolean";
}

export function isEnumParamSchemaEntry(v: ParamSchemaEntry): v is ParamEnumSchemaEntry {
  return "type" in v && v.type === "enum" && typeof v.value === "string" && "choices" in v;
}

function isParamNumberSchemaEntry(v: unknown): v is ParamNumberSchemaEntry {
  if (!isRecord(v)) return false;
  return (
    (v.type === undefined || typeof v.type === "string") &&
    typeof v.value === "number" &&
    typeof v.min === "number" &&
    typeof v.max === "number" &&
    typeof v.step === "number" &&
    typeof v.unit === "string" &&
    typeof v.desc === "string"
  );
}

function isParamBooleanSchemaEntry(v: unknown): v is ParamBooleanSchemaEntry {
  return (
    isRecord(v) &&
    v.type === "boolean" &&
    typeof v.value === "boolean" &&
    typeof v.desc === "string"
  );
}

function isParamEnumSchemaEntry(v: unknown): v is ParamEnumSchemaEntry {
  return (
    isRecord(v) &&
    v.type === "enum" &&
    typeof v.value === "string" &&
    Array.isArray(v.choices) &&
    v.choices.length > 0 &&
    v.choices.every((choice) => typeof choice === "string") &&
    new Set(v.choices).size === v.choices.length &&
    v.choices.includes(v.value) &&
    typeof v.desc === "string"
  );
}

function isParamSchemaEntry(v: unknown): v is ParamSchemaEntry {
  return isParamNumberSchemaEntry(v) || isParamBooleanSchemaEntry(v) || isParamEnumSchemaEntry(v);
}

/**
 * Parse + validate the contents of `model.json`.
 *
 * Returns a typed {@link ModelInfo} on success, or `null` if the input is empty,
 * not valid JSON, or fails structural validation. Never throws — callers can use
 * the result directly as render state.
 */
export function parseModelInfo(json: string | null | undefined): ModelInfo | null {
  if (!json) return null;

  let raw: unknown;
  try {
    raw = JSON.parse(json);
  } catch {
    return null;
  }

  if (!isRecord(raw)) return null;

  // Accept schema 1 (legacy history artifacts) and 2 (per-object appearance).
  if (raw.schema !== 1 && raw.schema !== 2) return null;
  if (typeof raw.buildId !== "number" || !Number.isFinite(raw.buildId)) return null;
  if (raw.units !== "mm") return null;

  if (!isRecord(raw.build)) return null;
  const build = raw.build;
  if (
    typeof build.ok !== "boolean" ||
    typeof build.durationMs !== "number" ||
    !Array.isArray(build.warnings) ||
    !build.warnings.every((w) => typeof w === "string")
  ) {
    return null;
  }

  if (!Array.isArray(raw.objects) || !raw.objects.every(isModelObject)) return null;
  const isEmpty = raw.objects.length === 0;

  const hasBBox =
    isRecord(raw.bbox) && isVec3(raw.bbox.size) && isVec3(raw.bbox.min) && isVec3(raw.bbox.max);
  // A final-part deletion has no extents or center. Older empty artifacts may
  // still carry zero-size extents, so retain that compatible representation.
  if ((!isEmpty && !hasBBox) || (isEmpty && !(hasBBox || raw.bbox === null))) return null;

  if (typeof raw.volume !== "number" || !Number.isFinite(raw.volume)) return null;
  if (
    (!isEmpty && !isVec3(raw.centerOfMass)) ||
    (isEmpty && !(isVec3(raw.centerOfMass) || raw.centerOfMass === null))
  ) {
    return null;
  }

  if (!isRecord(raw.mass)) return null;
  const mass = raw.mass;
  if (
    typeof mass.value !== "number" ||
    typeof mass.material !== "string" ||
    typeof mass.density !== "number"
  ) {
    return null;
  }

  if (typeof raw.valid !== "boolean" || typeof raw.manifold !== "boolean") return null;

  // params — sanitized, NOT rejected. A near-miss PARAMS schema (e.g. an agent
  // wrote a malformed entry) must never block geometry from rendering, so we
  // tolerantly keep only the well-formed bits rather than failing the manifest:
  //   • keep schema entries that are valid ParamSchemaEntry shapes;
  //   • keep typed `values` whose key survives in the sanitized schema;
  //   • if `params` is missing / not an object, fall back to empty maps.
  // (All other top-level validations above stay strict.)
  const params = sanitizeParams(raw.params);

  // Structurally validated — assert through to the typed shape, substituting
  // the sanitized params so the inspector's slider section degrades gracefully.
  return { ...(raw as unknown as ModelInfo), params };
}

/**
 * Tolerantly normalize a raw `params` block into the {@link ModelInfo} `params`
 * shape. Never throws and never rejects: drops malformed schema entries and any
 * `values` key that isn't a finite number or isn't in the kept schema.
 */
function sanitizeParams(raw: unknown): ModelInfo["params"] {
  if (!isRecord(raw)) return { schema: {}, values: {} };

  const schema: Record<string, ParamSchemaEntry> = Object.create(null);
  if (isRecord(raw.schema)) {
    for (const [key, entry] of Object.entries(raw.schema)) {
      if (isSafeParamKey(key) && isParamSchemaEntry(entry)) schema[key] = entry;
    }
  }

  const values: Record<string, ParamValue> = Object.create(null);
  if (isRecord(raw.values)) {
    for (const [key, v] of Object.entries(raw.values)) {
      if (!isSafeParamKey(key) || !Object.prototype.hasOwnProperty.call(schema, key)) continue;
      const entry = schema[key];
      if (isNumericParamSchemaEntry(entry) && typeof v === "number" && Number.isFinite(v)) {
        values[key] = v;
      } else if (isBooleanParamSchemaEntry(entry) && typeof v === "boolean") {
        values[key] = v;
      } else if (
        isEnumParamSchemaEntry(entry) &&
        typeof v === "string" &&
        entry.choices.includes(v)
      ) {
        values[key] = v;
      }
    }
  }

  return { schema, values };
}

function isSafeParamKey(key: string): boolean {
  return key !== "__proto__" && key !== "prototype" && key !== "constructor";
}
