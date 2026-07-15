import { engineCall, invoke } from "./core";

/* ───────────────────────────── engine RPC ─────────────────────────────── */

/**
 * Push new parameter values to the engine. The engine rebuilds the model, writes
 * fresh artifacts, and fires `model-updated`; the updated `model.params.values`
 * (flowing back through {@link readModelJson}) become the source of truth.
 *
 * @param values Partial map of `{ [paramKey]: value }` to apply.
 * @returns The raw engine response string, or `null` if the engine isn't ready.
 */
export async function engineSetParams(values: Record<string, number>): Promise<string | null> {
  return engineCall<string>("engine_set_params", { values });
}

/**
 * Read the engine's current parameter set. Returns the raw response string, or
 * `null` if the engine isn't ready / the call fails.
 */
export async function engineGetParams(): Promise<string | null> {
  return engineCall<string>("engine_get_params");
}

/**
 * Export the current model to `path` in the given `format` (`step`, `stl`,
 * `glb`, `gltf`, `brep`, `3mf`). Optional `options` carry per-format settings
 * validated by the engine. Returns the raw engine response string on success.
 *
 * @throws Re-throws on failure so callers can surface an inline error note.
 */
export async function engineExport(
  format: string,
  path: string,
  options?: Record<string, unknown>,
): Promise<string> {
  return invoke<string>("engine_export", { format, path, options: options ?? null });
}

/** Export a non-ready build after the app host issues a one-time override. */
export async function engineExportWithOverride(
  format: string,
  path: string,
  options?: Record<string, unknown>,
): Promise<string> {
  return invoke<string>("engine_export_with_override", { format, path, options: options ?? null });
}

/** Read the engine's four-state conformance findings, or null when unavailable. */
export async function engineGetConformance(): Promise<string | null> {
  return engineCall<string>("engine_get_conformance");
}

/** Read the engine's aggregate strict-export readiness, or null when unavailable. */
export async function engineGetReadiness(): Promise<string | null> {
  return engineCall<string>("engine_get_readiness");
}

/**
 * Ask the engine to re-render the current model (refresh GLB + manifest).
 * Returns the raw response string, or `null` if the engine isn't ready.
 */
export async function engineRender(): Promise<string | null> {
  return engineCall<string>("engine_render");
}

/**
 * Fetch the engine's current model manifest directly (parallel to reading
 * `model.json`). Returns the parsed manifest, or `null` if unavailable.
 */
export async function engineGetModelInfo(): Promise<unknown | null> {
  try {
    const raw = await invoke<string>("engine_get_model_info");
    return JSON.parse(raw) as unknown;
  } catch {
    return null;
  }
}

/**
 * Read the assembly's nested skeleton contract (scalars/frames/joints) plus each
 * child's occurrences, straight from the engine. Read-only; never rebuilds.
 * Returns the raw response string, or `null` when the engine isn't ready, the
 * workspace is a single model (the engine replies `ok:false`), or the backend
 * predates this command. Feed the result to `parseAssemblyTree`.
 */
export async function engineGetAssemblyTree(): Promise<string | null> {
  return engineCall<string>("engine_get_assembly_tree");
}

/**
 * Run a DFM (manufacturability) analysis on the current model. Read-only — it
 * never triggers a rebuild. Returns the raw engine response string, or `null`
 * if the engine isn't ready / the call fails. Feed the result to
 * `parseDfmReport`. Pass `process` to override per-part material inference
 * (currently only `fdm` is evaluated).
 */
export async function engineAnalyzeDfm(process?: string): Promise<string | null> {
  return engineCall<string>("engine_analyze_dfm", { process: process ?? null });
}

/**
 * Exact mass properties of the current model (per-part + assembly total). Returns
 * the raw engine JSON, or `null` if the engine isn't ready. Feed to `parseMeasureReport`.
 */
export async function engineMeasure(): Promise<string | null> {
  return engineCall<string>("engine_measure");
}

/**
 * First-order stress hot-spots (sharp internal corners). Returns the raw engine
 * JSON, or `null` if the engine isn't ready. Feed to `parseStressReport`.
 */
export async function engineStressCheck(): Promise<string | null> {
  return engineCall<string>("engine_stress_check");
}

/**
 * Compute a 1-D tolerance stack over an agent/user-supplied dimension chain.
 * Returns the raw engine JSON, or `null` on failure. Feed to `parseToleranceResult`.
 */
export async function engineToleranceStack(chain: unknown[]): Promise<string | null> {
  return engineCall<string>("engine_tolerance_stack", { chain });
}

/**
 * Evaluate the workspace's design requirements against the current model. Returns
 * the raw engine JSON, or `null` if the engine isn't ready. Feed to `parseRequirementsReport`.
 */
export async function engineCheckRequirements(): Promise<string | null> {
  return engineCall<string>("engine_check_requirements");
}

/**
 * Replace the workspace's design requirements (persisted per workspace). Returns
 * the raw engine JSON ({ok, count}), or `null` on failure.
 */
export async function engineSetRequirements(requirements: unknown[]): Promise<string | null> {
  return engineCall<string>("engine_set_requirements", { requirements });
}

/**
 * Sweep one parameter across `values` (non-destructive) and get a measured table.
 * Returns raw engine JSON or `null`. Feed to `parseSweepReport`.
 */
export async function engineSweep(
  param: string,
  values: number[],
  checks = false,
): Promise<string | null> {
  return engineCall<string>("engine_sweep", { param, values, checks });
}

/**
 * Optimize one parameter toward an objective under constraints. Returns raw
 * engine JSON or `null`. Feed to `parseOptimizeResult`.
 */
export async function engineOptimize(
  param: string,
  objective: "min_mass" | "max_mass",
  steps: number,
  constraints?: Record<string, unknown>,
): Promise<string | null> {
  return engineCall<string>("engine_optimize", { param, objective, steps, constraints });
}

/**
 * Sweep one shown part through a revolute/prismatic range and report collisions
 * with the other parts. Returns raw engine JSON or `null`.
 */
/**
 * Measure an imported (or shown) part into dimensions + detected features, for
 * reverse-engineering a parametric rebuild. Returns raw engine JSON or `null`.
 */
export async function engineAnalyzeImport(name?: string): Promise<string | null> {
  return engineCall<string>("engine_analyze_import", { name: name ?? null });
}

/**
 * Compare the current model to a past checkpoint (by history index): added /
 * removed material + scalar deltas. Returns raw engine JSON or `null`.
 */
export async function engineDiffAgainst(index: number): Promise<string | null> {
  return engineCall<string>("engine_diff_against", { index });
}

/**
 * Drive parameters toward spec compliance. Returns raw engine JSON or `null`.
 * Pass `apply=true` to commit the changes to the model.
 */
export async function engineConvergeToSpec(
  objective = "min_mass",
  apply = false,
): Promise<string | null> {
  return engineCall<string>("engine_converge_to_spec", { objective, apply });
}

/**
 * Write a printable spec sheet (report.html) for the current model and return the
 * raw engine JSON ({ok, path, summary}), or `null` on failure.
 */
export async function engineBuildReport(views?: string[]): Promise<string | null> {
  return engineCall<string>("engine_build_report", { views: views ?? null });
}

export async function engineCheckMotion(opts: {
  part: string;
  kind?: "revolute" | "prismatic";
  axisOrigin?: [number, number, number];
  axisDir?: [number, number, number];
  start?: number;
  stop?: number;
  steps?: number;
}): Promise<string | null> {
  return engineCall<string>("engine_check_motion", {
    part: opts.part,
    kind: opts.kind ?? "revolute",
    axisOrigin: opts.axisOrigin ?? null,
    axisDir: opts.axisDir ?? null,
    start: opts.start ?? 0,
    stop: opts.stop ?? 90,
    steps: opts.steps ?? 12,
  });
}

/* ───────────────────────────── imports ────────────────────────────────── */

/**
 * Open a native file picker for a CAD/mesh file to import (STEP/STP/BREP/STL).
 * Returns the absolute path, or `null` if the user cancelled / it's unavailable.
 */
export async function pickCadFile(): Promise<string | null> {
  return engineCall<string>("pick_cad_file");
}

/**
 * Import an external CAD/mesh file (absolute `path`) as a ghosted reference
 * fixture: the engine copies it into the workspace `assets/`, records it in
 * `imports.json`, and rebuilds. Mutating, so it emits `model-updated` and the
 * viewport refreshes via {@link onModelUpdated}. Re-throws on failure so the
 * caller can surface an inline error.
 */
export async function engineImportReference(path: string, name?: string): Promise<string> {
  return invoke<string>("engine_import_reference", { path, name: name ?? null });
}

/** Remove a reference import by id (from the manifest) and rebuild. */
export async function engineRemoveImport(id: string): Promise<string | null> {
  return engineCall<string>("engine_remove_import", { id });
}

/* ───────────────────────────── drawings ───────────────────────────────── */

/** A `create_drawing` result: the written files + chosen scale + optional note. */
export interface DrawingResult {
  ok: true;
  files: string[];
  scale: string | null;
  note: string | null;
}

/**
 * Generate a 2D technical drawing (multi-view + spec sheet) of the current
 * model, writing a PDF (+ SVG alongside) to `path`. Returns the parsed result.
 * Re-throws on failure so the caller can surface an inline error.
 */
export async function engineCreateDrawing(
  path: string,
  options?: Record<string, unknown>,
): Promise<DrawingResult> {
  const raw = await invoke<string>("engine_create_drawing", { path, options: options ?? null });
  return JSON.parse(raw) as DrawingResult;
}

/** One feature in an `inspect_features` / `feature_at` match. */
export interface EngineFeature {
  name: string;
  kind: string | null;
  driven_by: string[];
  source: { line: number | null };
  center: [number, number, number] | null;
  bbox: [number, number, number] | null;
  metrics: { faces: number; geom_types: string[] } | null;
  inferred: boolean;
  confidence: number | null;
}

/** Resolve a 3D point (build123d Z-up mm) to the nearest feature, or null. */
export async function engineFeatureAt(
  point: [number, number, number],
): Promise<EngineFeature | null> {
  try {
    const raw = await invoke<string>("engine_feature_at", { point });
    return (JSON.parse(raw) as { match: EngineFeature | null }).match;
  } catch {
    return null;
  }
}

/** Change a named feature by adjusting its driving param(s). Raw response, or null. */
export async function engineSetFeature(
  name: string,
  values: Record<string, number>,
): Promise<string | null> {
  return engineCall<string>("engine_set_feature", { name, values });
}

/**
 * Assign a material to a specific part (or clear it with `material = null`, back
 * to the model's own material). Returns the raw engine response, or null if the
 * engine isn't ready. The viewport refreshes via the `model-updated` event the
 * Rust proxy emits.
 */
export async function setPartMaterial(
  partId: string,
  material: string | null,
): Promise<string | null> {
  return engineCall<string>("engine_set_part_material", { partId, material });
}
