import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { invoke } from "./core";

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
  publicationId?: string;
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
