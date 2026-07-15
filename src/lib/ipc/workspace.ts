import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { engineCall, invoke } from "./core";

/* ───────────────────────── workspace + artifacts ───────────────────────── */

/**
 * Absolute path of the engine workspace directory (where the PTY shell runs and
 * the engine writes immutable model generations).
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
 * One immutable manifest + GLB publication. `publicationId` is absent only when
 * reading root compatibility mirrors from an engine predating current.json.
 */
export interface ModelSnapshot {
  publicationId: string | null;
  manifest: string;
  glb: number[];
}

export async function readModelSnapshot(wsId?: string): Promise<ModelSnapshot | null> {
  return invoke<ModelSnapshot | null>("read_model_snapshot", { wsId });
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
  return engineCall<string>("engine_get_workspace_meta");
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
