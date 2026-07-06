/**
 * Typed wrappers over the Rust PTY host commands (see `src-tauri/src/pty.rs`).
 *
 * The Rust commands declare snake_case params (`on_data`, `rows`, `cols`, `data`).
 * Tauri v2 maps JS camelCase arg keys to Rust snake_case params automatically,
 * so we pass `onData` here and Tauri delivers it to the `on_data: Channel<Vec<u8>>`
 * parameter. The other params are already single-word, so the key is identical.
 *
 * Output is streamed over a Tauri **Channel** (not events). The Rust side sends
 * `Vec<u8>`; on the JS side that arrives as a `number[]`, which we convert to a
 * `Uint8Array` before handing it to xterm.
 */
import { invoke, Channel } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";

/** Options accepted by {@link ptySpawn}. */
export interface PtySpawnOptions {
  /** Working directory for the shell. Defaults (Rust-side) to $HOME. */
  cwd?: string;
  env?: Record<string, string>;
}

/**
 * Spawn the shell inside a real PTY and stream its raw output to `onData`.
 *
 * @param wsId   Workspace root path — keys the per-workspace PTY session.
 * @param onData Receives every chunk of terminal output as raw bytes.
 * @param opts   Optional working directory / environment overrides.
 */
export async function ptySpawn(
  wsId: string,
  onData: (bytes: Uint8Array) => void,
  opts: PtySpawnOptions = {},
): Promise<void> {
  // `Channel<number[]>` matches the Rust `Channel<Vec<u8>>` payload shape.
  const channel = new Channel<number[]>();
  channel.onmessage = (nums) => onData(Uint8Array.from(nums));

  await invoke("pty_spawn", {
    wsId,
    // camelCase `onData` -> Rust `on_data` (Tauri v2 default arg mapping).
    onData: channel,
    cwd: opts.cwd ?? null,
    env: opts.env ?? null,
  });
}

/** Write raw bytes (keystrokes) to the PTY. */
export async function ptyWrite(wsId: string, data: Uint8Array): Promise<void> {
  // Tauri serializes `Uint8Array` directly to a Rust `Vec<u8>` for the `data` param.
  await invoke("pty_write", { wsId, data });
}

/** Resize the PTY to the given terminal dimensions. */
export async function ptyResize(wsId: string, rows: number, cols: number): Promise<void> {
  await invoke("pty_resize", { wsId, rows, cols });
}

/* ───────────────────────── workspace + artifacts ───────────────────────── */

/**
 * Absolute path of the engine workspace directory (where the PTY shell runs and
 * the engine writes `model.json` / `model.glb`).
 */
export async function getWorkspaceDir(): Promise<string> {
  return invoke<string>("get_workspace_dir");
}

/**
 * Absolute path to the workspace's `exports/` folder, created if missing. This
 * is the default location exports land in, so the Save dialog opens here.
 */
export async function getExportDir(): Promise<string> {
  return invoke<string>("get_export_dir");
}

/**
 * Reveal the active workspace folder ("workspace") or its exports/ ("exports")
 * in the OS file manager. The Rust side resolves the path from the active
 * workspace, so no path is sent from the webview (least privilege: the opener
 * plugin no longer grants the webview an unscoped open-path).
 */
export async function revealWorkspaceDir(which: "workspace" | "exports"): Promise<void> {
  await invoke("reveal_workspace_dir", { which });
}

/**
 * Whether the workspace at `wsPath` has a `model.py` yet (agent has built at least
 * once). Drives the viewport's loading-vs-empty state. Resolves false on error.
 */
export async function workspaceHasModel(wsPath: string): Promise<boolean> {
  try {
    return await invoke<boolean>("workspace_has_model", { path: wsPath });
  } catch {
    return false;
  }
}

/**
 * Read the `model.json` render manifest as a raw string, or `null` if no build
 * has produced one yet. Feed the result to `parseModelInfo`.
 *
 * Pass `wsId` (the workspace root path) to read that workspace's artifacts
 * directly — prevents a wrong-workspace read when the backend focus hasn't
 * caught up yet. Omit to fall back to the focused workspace.
 */
export async function readModelJson(wsId?: string): Promise<string | null> {
  return invoke<string | null>("read_model_json", { wsId });
}

/**
 * Read the `model.glb` bytes. The Rust side returns a `tauri::ipc::Response`,
 * so the bytes arrive as an `ArrayBuffer` (not a JSON `number[]`); we wrap it in a
 * `Uint8Array` view — O(1), no per-byte copy — for the GLTF loader. This avoids
 * serializing/deserializing millions of array elements per build on a large mesh.
 *
 * Pass `wsId` to read a specific workspace's GLB; omit to use the focused one.
 *
 * Throws (rejects) if no GLB exists yet — callers should guard with try/catch.
 */
export async function readModelGlb(wsId?: string): Promise<Uint8Array> {
  const buf = await invoke<ArrayBuffer>("read_model_glb", { wsId });
  return new Uint8Array(buf);
}

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
  try {
    return await invoke<string>("engine_set_params", { values });
  } catch {
    return null;
  }
}

/**
 * Read the engine's current parameter set. Returns the raw response string, or
 * `null` if the engine isn't ready / the call fails.
 */
export async function engineGetParams(): Promise<string | null> {
  try {
    return await invoke<string>("engine_get_params");
  } catch {
    return null;
  }
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

/**
 * Ask the engine to re-render the current model (refresh GLB + manifest).
 * Returns the raw response string, or `null` if the engine isn't ready.
 */
export async function engineRender(): Promise<string | null> {
  try {
    return await invoke<string>("engine_render");
  } catch {
    return null;
  }
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
 * Run a DFM (manufacturability) analysis on the current model. Read-only — it
 * never triggers a rebuild. Returns the raw engine response string, or `null`
 * if the engine isn't ready / the call fails. Feed the result to
 * `parseDfmReport`. Pass `process` to override per-part material inference
 * (currently only `fdm` is evaluated).
 */
export async function engineAnalyzeDfm(process?: string): Promise<string | null> {
  try {
    return await invoke<string>("engine_analyze_dfm", { process: process ?? null });
  } catch {
    return null;
  }
}

/**
 * Exact mass properties of the current model (per-part + assembly total). Returns
 * the raw engine JSON, or `null` if the engine isn't ready. Feed to `parseMeasureReport`.
 */
export async function engineMeasure(): Promise<string | null> {
  try {
    return await invoke<string>("engine_measure");
  } catch {
    return null;
  }
}

/**
 * First-order stress hot-spots (sharp internal corners). Returns the raw engine
 * JSON, or `null` if the engine isn't ready. Feed to `parseStressReport`.
 */
export async function engineStressCheck(): Promise<string | null> {
  try {
    return await invoke<string>("engine_stress_check");
  } catch {
    return null;
  }
}

/**
 * Compute a 1-D tolerance stack over an agent/user-supplied dimension chain.
 * Returns the raw engine JSON, or `null` on failure. Feed to `parseToleranceResult`.
 */
export async function engineToleranceStack(chain: unknown[]): Promise<string | null> {
  try {
    return await invoke<string>("engine_tolerance_stack", { chain });
  } catch {
    return null;
  }
}

/**
 * Evaluate the workspace's design requirements against the current model. Returns
 * the raw engine JSON, or `null` if the engine isn't ready. Feed to `parseRequirementsReport`.
 */
export async function engineCheckRequirements(): Promise<string | null> {
  try {
    return await invoke<string>("engine_check_requirements");
  } catch {
    return null;
  }
}

/**
 * Replace the workspace's design requirements (persisted per workspace). Returns
 * the raw engine JSON ({ok, count}), or `null` on failure.
 */
export async function engineSetRequirements(requirements: unknown[]): Promise<string | null> {
  try {
    return await invoke<string>("engine_set_requirements", { requirements });
  } catch {
    return null;
  }
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
  try {
    return await invoke<string>("engine_sweep", { param, values, checks });
  } catch {
    return null;
  }
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
  try {
    return await invoke<string>("engine_optimize", { param, objective, steps, constraints });
  } catch {
    return null;
  }
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
  try {
    return await invoke<string>("engine_analyze_import", { name: name ?? null });
  } catch {
    return null;
  }
}

/**
 * Compare the current model to a past checkpoint (by history index): added /
 * removed material + scalar deltas. Returns raw engine JSON or `null`.
 */
export async function engineDiffAgainst(index: number): Promise<string | null> {
  try {
    return await invoke<string>("engine_diff_against", { index });
  } catch {
    return null;
  }
}

/**
 * Drive parameters toward spec compliance. Returns raw engine JSON or `null`.
 * Pass `apply=true` to commit the changes to the model.
 */
export async function engineConvergeToSpec(
  objective = "min_mass",
  apply = false,
): Promise<string | null> {
  try {
    return await invoke<string>("engine_converge_to_spec", { objective, apply });
  } catch {
    return null;
  }
}

/**
 * Write a printable spec sheet (report.html) for the current model and return the
 * raw engine JSON ({ok, path, summary}), or `null` on failure.
 */
export async function engineBuildReport(views?: string[]): Promise<string | null> {
  try {
    return await invoke<string>("engine_build_report", { views: views ?? null });
  } catch {
    return null;
  }
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
  try {
    return await invoke<string>("engine_check_motion", {
      part: opts.part,
      kind: opts.kind ?? "revolute",
      axisOrigin: opts.axisOrigin ?? null,
      axisDir: opts.axisDir ?? null,
      start: opts.start ?? 0,
      stop: opts.stop ?? 90,
      steps: opts.steps ?? 12,
    });
  } catch {
    return null;
  }
}

/* ───────────────────────────── imports ────────────────────────────────── */

/**
 * Open a native file picker for a CAD/mesh file to import (STEP/STP/BREP/STL).
 * Returns the absolute path, or `null` if the user cancelled / it's unavailable.
 */
export async function pickCadFile(): Promise<string | null> {
  try {
    return (await invoke<string | null>("pick_cad_file")) ?? null;
  } catch {
    return null;
  }
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
  try {
    return await invoke<string>("engine_remove_import", { id });
  } catch {
    return null;
  }
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

/* ───────────────────────────── history ────────────────────────────────── */

/** One entry in the workspace edit history (a git commit). */
export interface HistoryEntry {
  index: number;
  sha: string;
  message: string;
  /** Commit time, epoch seconds. */
  time: number;
  /** True for the entry currently shown in the viewport. */
  current: boolean;
}

/** The engine's `history` response: ordered entries + the current index. */
export interface HistoryState {
  entries: HistoryEntry[];
  index: number;
}

/** Read the workspace edit history, or `null` if the engine isn't ready. */
export async function engineHistory(): Promise<HistoryState | null> {
  try {
    return JSON.parse(await invoke<string>("engine_history")) as HistoryState;
  } catch {
    return null;
  }
}

/** Undo the last edit. Returns the raw engine response, or `null` if unavailable. */
export async function engineUndo(): Promise<string | null> {
  try {
    return await invoke<string>("engine_undo");
  } catch {
    return null;
  }
}

/** Redo the last undone edit. Returns the raw response, or `null` if unavailable. */
export async function engineRedo(): Promise<string | null> {
  try {
    return await invoke<string>("engine_redo");
  } catch {
    return null;
  }
}

/** Jump to history entry `index`. Returns the raw response, or `null` if unavailable. */
export async function engineGoto(index: number): Promise<string | null> {
  try {
    return await invoke<string>("engine_goto", { index });
  } catch {
    return null;
  }
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
  try {
    return await invoke<string>("engine_set_feature", { name, values });
  } catch {
    return null;
  }
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
  try {
    return await invoke<string>("engine_set_part_material", { partId, material });
  } catch {
    return null;
  }
}

/* ─────────────────────────────── events ───────────────────────────────── */

/** Engine lifecycle states broadcast on the `engine-status` event. */
export type EngineStatus = "provisioning" | "updating" | "ready" | "error";

/** Payload of the `engine-status` event. */
export interface EngineStatusEvent {
  status: EngineStatus;
  interpreter: string | null;
  version: string | null;
  message: string | null;
  /**
   * The workspace path this status belongs to, when the event is tab-scoped.
   * Null/absent for the legacy single-engine view. Keys the per-tab dots in
   * {@link WorkspaceSwitcher} via {@link useWorkspaceStatuses}.
   */
  wsId?: string | null;
  /** 0..1 download fraction while `status === "updating"`; null otherwise. */
  progress?: number | null;
}

/** Payload of the `model-updated` event. */
export interface ModelUpdatedEvent {
  buildId: number;
}

/**
 * Fetch the engine's *current* lifecycle status on demand.
 *
 * The `engine-status` event is emitted once at boot; a listener that mounts
 * after that emit (webview reload, or a render-before-emit race) would never
 * hear "ready". Querying this command on mount closes that gap — the Rust
 * `get_engine_status` command returns the same `{ status, interpreter, version,
 * message }` shape as the event.
 *
 * Resolves to `null` (rather than throwing) when the command is unavailable —
 * e.g. an older backend build that predates it — so callers fall back silently
 * to the provisioning default.
 */
export async function getEngineStatus(): Promise<EngineStatusEvent | null> {
  try {
    return await invoke<EngineStatusEvent>("get_engine_status");
  } catch {
    return null;
  }
}

/** Snapshot of every live engine's status (each carries `wsId`). Used to seed the
 *  switcher's per-tab dots on mount (engines don't re-emit after a frontend reload). */
export async function getEngineStatuses(): Promise<EngineStatusEvent[]> {
  try {
    return await invoke<EngineStatusEvent[]>("get_engine_statuses");
  } catch {
    return [];
  }
}

/**
 * Subscribe to engine lifecycle changes. Returns an unlisten function (or a
 * no-op cleanup if the listener fails to attach, e.g. backend not ready).
 */
export async function onEngineStatus(
  handler: (payload: EngineStatusEvent) => void,
): Promise<UnlistenFn> {
  return listen<EngineStatusEvent>("engine-status", (event) => handler(event.payload));
}

/**
 * Subscribe to fresh-build notifications. Returns an unlisten function (or a
 * no-op cleanup if the listener fails to attach).
 */
export async function onModelUpdated(
  handler: (payload: ModelUpdatedEvent) => void,
): Promise<UnlistenFn> {
  return listen<ModelUpdatedEvent>("model-updated", (event) => handler(event.payload));
}

/** Payload of the `workspace-meta-updated` event. */
export interface WorkspaceMetaUpdatedEvent {
  wsId: string;
}

/**
 * Subscribe to workspace metadata change notifications (description, tags,
 * proposedName). Returns an unlisten function.
 */
export async function onWorkspaceMetaUpdated(
  handler: (payload: WorkspaceMetaUpdatedEvent) => void,
): Promise<UnlistenFn> {
  return listen<WorkspaceMetaUpdatedEvent>("workspace-meta-updated", (e) => handler(e.payload));
}

/** Read the focused engine's workspace metadata (raw engine JSON string or null). */
export async function getWorkspaceMeta(): Promise<string | null> {
  try {
    return await invoke<string>("engine_get_workspace_meta");
  } catch {
    return null;
  }
}

/** Payload of the `build-brief-updated` event. */
export interface BuildBriefUpdatedEvent {
  wsId: string;
}

/** Read the build brief recorded for a workspace (parsed JSON, or null if none). */
export async function getBuildBrief(wsPath: string): Promise<unknown> {
  return invoke("get_build_brief", { wsPath });
}

/**
 * Subscribe to build-brief change notifications (the engine wrote build_brief.json).
 * Returns an unlisten function.
 */
export async function onBuildBriefUpdated(
  handler: (payload: BuildBriefUpdatedEvent) => void,
): Promise<UnlistenFn> {
  return listen<BuildBriefUpdatedEvent>("build-brief-updated", (e) => handler(e.payload));
}

/* ───────────────────────────── app-config ─────────────────────────────── */

/** How the app applies an available update (mirrors the Rust contract). */
export type UpdateBehavior = "notify" | "autoDownload" | "silent";
/** Release channel the updater checks. */
export type UpdateChannel = "stable" | "beta";

/** Global app config (mirrors the Rust `AppConfig` camelCase contract): viewport
 *  feature flags plus update behavior, channel, and the last-seen app version. */
export interface AppConfig {
  gtao: boolean;
  grid: boolean;
  smaa: boolean;
  softShadows: boolean;
  updateBehavior: UpdateBehavior;
  updateChannel: UpdateChannel;
  /** App version whose what's-new the user has seen; null until first dismiss. */
  lastSeenVersion: string | null;
  /** Home library view mode. */
  homeView: "grid" | "list";
  /** Home library filter. */
  homeFilter: "all" | "recent" | "archived";
  /** Workspace path whose continue-hero was dismissed, or null. */
  homeHeroDismissed: string | null;
}

/** The shipped defaults; used when the backend is unavailable so the UI never crashes. */
export const DEFAULT_APP_CONFIG: AppConfig = {
  gtao: true,
  grid: true,
  smaa: true,
  softShadows: true,
  updateBehavior: "notify",
  updateChannel: "stable",
  lastSeenVersion: null,
  homeView: "grid",
  homeFilter: "all",
  homeHeroDismissed: null,
};

const UPDATE_BEHAVIORS: readonly UpdateBehavior[] = ["notify", "autoDownload", "silent"];
const UPDATE_CHANNELS: readonly UpdateChannel[] = ["stable", "beta"];

/** Validate + normalize a raw app-config record, filling any missing field from defaults. */
function toAppConfig(v: unknown): AppConfig {
  if (typeof v !== "object" || v === null) return DEFAULT_APP_CONFIG;
  const r = v as Record<string, unknown>;
  return {
    gtao: typeof r.gtao === "boolean" ? r.gtao : DEFAULT_APP_CONFIG.gtao,
    grid: typeof r.grid === "boolean" ? r.grid : DEFAULT_APP_CONFIG.grid,
    smaa: typeof r.smaa === "boolean" ? r.smaa : DEFAULT_APP_CONFIG.smaa,
    softShadows:
      typeof r.softShadows === "boolean" ? r.softShadows : DEFAULT_APP_CONFIG.softShadows,
    updateBehavior: UPDATE_BEHAVIORS.includes(r.updateBehavior as UpdateBehavior)
      ? (r.updateBehavior as UpdateBehavior)
      : DEFAULT_APP_CONFIG.updateBehavior,
    updateChannel: UPDATE_CHANNELS.includes(r.updateChannel as UpdateChannel)
      ? (r.updateChannel as UpdateChannel)
      : DEFAULT_APP_CONFIG.updateChannel,
    lastSeenVersion: typeof r.lastSeenVersion === "string" ? r.lastSeenVersion : null,
    homeView: r.homeView === "list" ? "list" : DEFAULT_APP_CONFIG.homeView,
    homeFilter:
      r.homeFilter === "recent" || r.homeFilter === "archived"
        ? r.homeFilter
        : DEFAULT_APP_CONFIG.homeFilter,
    homeHeroDismissed: typeof r.homeHeroDismissed === "string" ? r.homeHeroDismissed : null,
  };
}

/**
 * Read the global app-config. Resolves to {@link DEFAULT_APP_CONFIG} on any
 * failure (command unavailable, backend not ready) so the viewport always has a
 * valid config.
 */
export async function getAppConfig(): Promise<AppConfig> {
  try {
    return toAppConfig(await invoke<unknown>("get_app_config"));
  } catch {
    return DEFAULT_APP_CONFIG;
  }
}

/**
 * Apply a PARTIAL patch (only the changed flags) to the global app-config and
 * persist it. Returns the merged, authoritative config from the backend.
 *
 * @throws Re-throws the backend error so the store can revert the optimistic
 *   toggle and surface a non-blocking message.
 */
export async function setAppConfig(patch: Partial<AppConfig>): Promise<AppConfig> {
  return toAppConfig(await invoke<unknown>("set_app_config", { patch }));
}

/* ─────────────────────────────── updater ──────────────────────────────── */

/** Result of an update check: whether one is available and (if so) its version. */
export interface UpdateCheck {
  available: boolean;
  version: string | null;
}

/**
 * Check the given release channel for an available update (Rust `check_for_update`).
 * Re-throws on failure so the caller can surface the error state.
 */
export async function checkForUpdate(channel: UpdateChannel): Promise<UpdateCheck> {
  return invoke<UpdateCheck>("check_for_update", { channel });
}

/**
 * Download and install the available update for the channel (Rust
 * `download_and_install`). Resolves when the install finishes; download progress
 * arrives on the `updater://progress` event. Re-throws on failure.
 */
export async function downloadAndInstall(channel: UpdateChannel): Promise<void> {
  await invoke("download_and_install", { channel });
}

/* ──────────────────────────── agent-config ────────────────────────────── */

/** One available workspace skill with its enabled state (mirrors Rust `SkillInfo`). */
export interface SkillInfo {
  name: string;
  description: string;
  enabled: boolean;
}

/** Per-workspace agent config (mirrors the Rust `AgentConfig` camelCase contract). */
export interface AgentConfig {
  /** Enabled skill names, or `null` ⇒ all skills enabled (the shipped default). */
  enabledSkills: string[] | null;
  /** Whether the provisioner manages (writes) the workspace skill tree. */
  autoProvisionSkills: boolean;
}

/**
 * List the active workspace's available skills + enabled state. Resolves to `[]`
 * on failure (no workspace open / command unavailable) so settings degrades to an
 * empty (non-crashing) state.
 */
export async function listSkills(): Promise<SkillInfo[]> {
  try {
    const raw = await invoke<unknown>("list_skills");
    if (!Array.isArray(raw)) return [];
    return raw.filter(
      (s): s is SkillInfo =>
        typeof s === "object" &&
        s !== null &&
        typeof (s as SkillInfo).name === "string" &&
        typeof (s as SkillInfo).description === "string" &&
        typeof (s as SkillInfo).enabled === "boolean",
    );
  } catch {
    return [];
  }
}

/** Read the active workspace's agent config, or `null` on failure / no workspace. */
export async function getAgentConfig(): Promise<AgentConfig | null> {
  try {
    const raw = await invoke<unknown>("get_agent_config");
    if (typeof raw !== "object" || raw === null) return null;
    const r = raw as Record<string, unknown>;
    const enabledSkills = Array.isArray(r.enabledSkills)
      ? (r.enabledSkills.filter((x) => typeof x === "string") as string[])
      : null;
    return {
      enabledSkills,
      autoProvisionSkills: r.autoProvisionSkills === true,
    };
  } catch {
    return null;
  }
}

/**
 * Persist the active workspace's agent config. The new skill set takes effect on
 * the next workspace open (the provisioner re-runs).
 *
 * @throws Re-throws the backend error so the settings UI can surface it inline.
 */
export async function setAgentConfig(config: AgentConfig): Promise<AgentConfig> {
  await invoke("set_agent_config", { config });
  return config;
}

/* ───────────────────────────── fabrication ────────────────────────────── */

/** Detect the installed slicer / fabrication tool. Returns raw engine JSON or `null`. */
export async function engineFabDetect(): Promise<string | null> {
  try {
    return await invoke<string>("engine_fab_detect");
  } catch {
    return null;
  }
}

/** Estimate print time / filament for a destination. Returns raw engine JSON or `null`. */
export async function engineFabEstimate(destinationId?: string | null): Promise<string | null> {
  try {
    return await invoke<string>("engine_fab_estimate", { destinationId: destinationId ?? null });
  } catch {
    return null;
  }
}

/**
 * Suggest the best print orientation to minimise overhangs. Returns raw engine
 * JSON or `null`. Leave `overhangDeg` unset to use the workspace's manufacturing
 * profile (process.overhangDeg), so this matches what Sol's fab_orient does.
 */
export async function engineFabOrient(overhangDeg?: number): Promise<string | null> {
  try {
    const args = overhangDeg === undefined ? {} : { overhangDeg };
    return await invoke<string>("engine_fab_orient", args);
  } catch {
    return null;
  }
}

/** Open (slice / send) the model to a fabrication destination. Returns raw engine JSON or `null`. */
export async function engineFabOpen(destinationId?: string | null): Promise<string | null> {
  try {
    return await invoke<string>("engine_fab_open", { destinationId: destinationId ?? null });
  } catch {
    return null;
  }
}

/**
 * App-level fabrication data is served natively (not via the workspace engine),
 * so the Factory page works without a workspace open. These mirror the materials
 * commands: they throw on failure and the caller decides how to surface it.
 */

/** Configured print destinations (connections) from the app config store. */
export async function getDestinations(): Promise<import("./fabrication").Destination[]> {
  return await invoke<import("./fabrication").Destination[]>("get_destinations");
}

/** Persist the destination list; returns the reloaded authoritative copy. */
export async function setDestinations(
  destinations: import("./fabrication").Destination[],
): Promise<import("./fabrication").Destination[]> {
  return await invoke<import("./fabrication").Destination[]>("set_destinations", { destinations });
}

/** Printer + filament profile names discovered from the installed slicer. */
export async function getSlicerProfiles(): Promise<import("./fabrication").ProfileSet> {
  return await invoke<import("./fabrication").ProfileSet>("get_slicer_profiles");
}

/** Supported slicers with detection status + override, for Settings → Slicers. */
export async function getSlicerConfig(): Promise<import("./fabrication").SlicerEntry[]> {
  return await invoke<import("./fabrication").SlicerEntry[]>("get_slicer_config");
}

/** Set (or clear, with `null`) a slicer's binary override; returns refreshed config. */
export async function setSlicerOverride(
  id: string,
  executablePath: string | null,
): Promise<import("./fabrication").SlicerEntry[]> {
  return await invoke<import("./fabrication").SlicerEntry[]>("set_slicer_override", {
    id,
    executablePath,
  });
}

/** Native picker for a slicer executable (a macOS `.app` is accepted). */
export async function pickSlicerBinary(): Promise<string | null> {
  return (await invoke<string | null>("pick_slicer_binary")) ?? null;
}

/* ─────────────────────────────── reference library ────────────────────────────── */

/** A single reference part entry (seed or user-added). */
export interface ReferenceEntry {
  id: string;
  category: string;
  dims_mm: Record<string, number | number[]>;
  source: string;
  aliases?: string[];
  mounting_holes?: Record<string, unknown>;
  notes?: string;
  origin?: "learned" | "manual";
  verified_at?: string;
  verified_in?: string;
}

/** The full reference library split into seed (built-in) and user entries. */
export interface ReferenceLibrary {
  seed: ReferenceEntry[];
  user: ReferenceEntry[];
}

/** Read the full reference library (seed + user entries). Re-throws on failure. */
export async function getReferenceLibrary(): Promise<ReferenceLibrary> {
  return invoke("get_reference_library");
}

/**
 * Persist a new or updated reference entry (stamps `origin: "manual"` server-side).
 * Re-throws on failure so the caller can surface the error.
 */
export async function saveReferenceEntry(entry: ReferenceEntry): Promise<unknown> {
  return invoke("save_reference_entry", { entry });
}

/**
 * Delete the user reference entry with the given `id`.
 * Re-throws on failure so the caller can surface the error.
 */
export async function deleteReferenceEntry(id: string): Promise<unknown> {
  return invoke("delete_reference_entry", { id });
}

/**
 * Subscribe to reference-library change notifications (any write via GUI or Sol).
 * Returns an unlisten function.
 */
export async function onReferenceLibraryUpdated(handler: () => void): Promise<UnlistenFn> {
  return listen("reference-library-updated", () => handler());
}
