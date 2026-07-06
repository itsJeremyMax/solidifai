/**
 * useUpdater — pure decision logic + shared types for the in-app updater.
 *
 * The stateful, impure part (auto-check on launch, download/progress, restart)
 * lives in the single app-wide `UpdaterProvider` (src/state/updater.tsx); the
 * `useUpdater()` consumer hook is exported from there. This module holds only the
 * pure `nextActionFor` decision (tested in useUpdater.test.ts) and the types both
 * sides share.
 */
import type { UpdateBehavior } from "../lib/ipc";

/** What to do once a check resolves, given the user's behavior. */
export type UpdateAction = "idle" | "show-indicator" | "download" | "download-silent";

export type UpdateStatus = "idle" | "available" | "downloading" | "ready" | "error";

/**
 * Pure: map an update-behavior + availability to the next action. No update ⇒
 * always `idle`. Otherwise notify⇒show-indicator, autoDownload⇒download,
 * silent⇒download-silent.
 */
export function nextActionFor(behavior: UpdateBehavior, available: boolean): UpdateAction {
  if (!available) return "idle";
  switch (behavior) {
    case "notify":
      return "show-indicator";
    case "autoDownload":
      return "download";
    case "silent":
      return "download-silent";
  }
}

/** The shared updater state + actions provided by `UpdaterProvider`. */
export interface UseUpdaterResult {
  /** Lifecycle state for the indicator to render. */
  status: UpdateStatus;
  /** The available version (e.g. "1.4.0"), or null when none / unknown. */
  version: string | null;
  /** Download progress 0..1 when the total is known, else null (indeterminate). */
  progress: number | null;
  /** Last error message, or null. */
  error: string | null;
  /** Begin download+install. Used by the indicator when behavior is "notify". */
  startDownload: () => void;
  /** Relaunch the app to apply an installed update. */
  restart: () => void;
  /**
   * Manually re-check the configured channel; returns the result. `error` is
   * set (and `available` false) when the check itself failed.
   */
  checkNow: () => Promise<{ available: boolean; version: string | null; error: string | null }>;
}
