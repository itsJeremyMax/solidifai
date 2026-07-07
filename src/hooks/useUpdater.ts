/**
 * useUpdater — pure decision logic + shared types for the in-app updater.
 *
 * The stateful, impure part (auto-check on launch, periodic + focus re-checks,
 * download/progress, restart) lives in the single app-wide `UpdaterProvider`
 * (src/state/updater.tsx); the `useUpdater()` consumer hook is exported from
 * there. This module holds only the pure decisions (tested in useUpdater.test.ts)
 * and the types both sides share.
 */
import type { UpdateBehavior } from "../lib/ipc";

/** What to do once a check resolves, given the user's behavior. */
export type UpdateAction = "idle" | "show-indicator" | "download" | "download-silent";

/**
 * Lifecycle state for the indicator + companion card to render.
 *   • idle        — nothing to show.
 *   • checking    — a manual re-check is in flight (background checks don't set this).
 *   • available   — an update exists and is waiting for the user to start it.
 *   • downloading — the install is streaming (see `progress`).
 *   • ready       — installed, waiting for a restart to apply.
 *   • error       — a download failed and can be retried.
 */
export type UpdateStatus = "idle" | "checking" | "available" | "downloading" | "ready" | "error";

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

/** How long the app waits between automatic background update checks. */
export const PERIODIC_CHECK_INTERVAL_MS = 6 * 60 * 60 * 1000; // 6 hours
/** The minimum gap before a window-focus re-check runs, so tab-switching is cheap. */
export const FOCUS_CHECK_THROTTLE_MS = 30 * 60 * 1000; // 30 minutes

/**
 * Pure: should an automatic re-check run now? True when nothing has been checked
 * yet, or when at least `minIntervalMs` has passed since the last check. Drives
 * both the periodic timer and the throttled window-focus listener.
 */
export function shouldRunPeriodicCheck(
  lastCheckedAt: number | null,
  now: number,
  minIntervalMs: number,
): boolean {
  if (lastCheckedAt === null) return true;
  return now - lastCheckedAt >= minIntervalMs;
}

/** The shared updater state + actions provided by `UpdaterProvider`. */
export interface UseUpdaterResult {
  /** Lifecycle state for the indicator to render. */
  status: UpdateStatus;
  /** The available version (e.g. "1.4.0"), or null when none / unknown. */
  version: string | null;
  /** Release notes (markdown) for the available version, or null when unknown. */
  notes: string | null;
  /** Download progress 0..1 when the total is known, else null (indeterminate). */
  progress: number | null;
  /** Last error message, or null. */
  error: string | null;
  /** Epoch ms of the last completed check (any trigger), or null before the first. */
  lastCheckedAt: number | null;
  /**
   * Whether the user has dismissed the companion card for the current moment.
   * The header pill stays; the card hides until the next louder state (ready/error).
   */
  dismissed: boolean;
  /** Begin download+install. Used by the indicator/card when behavior is "notify". */
  startDownload: () => void;
  /** Relaunch the app to apply an installed update. */
  restart: () => void;
  /** Hide the companion card for now (collapses to the header pill). */
  dismiss: () => void;
  /**
   * Manually re-check the configured channel; returns the result. `error` is
   * set (and `available` false) when the check itself failed.
   */
  checkNow: () => Promise<{ available: boolean; version: string | null; error: string | null }>;
}
