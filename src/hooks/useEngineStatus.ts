/**
 * useEngineStatus — subscribes to the Rust `engine-status` event and exposes a
 * presentation-ready view of the engine's lifecycle for {@link EngineStatusPill}.
 *
 * The engine moves through `provisioning → ready` (or `error`) as it resolves a
 * Python interpreter and warms the build environment. We map each raw status to
 * a human label and surface the resolved `version` string for the mono build tag.
 *
 * Failures to attach the listener (e.g. the app rendering before the Tauri
 * backend is up) degrade silently to the idle `provisioning` state so the UI
 * never blocks on the engine.
 *
 * The "ready" event is emitted once at boot. To survive a listener that mounts
 * *after* that emit (webview reload, or a render-before-emit race), we also
 * query the current status on mount via `getEngineStatus()` and seed the view
 * from it before attaching the live listener.
 */
import { useEffect, useState } from "react";

import {
  getEngineStatus,
  getEngineStatuses,
  onEngineStatus,
  type EngineStatus,
  type EngineStatusEvent,
} from "../lib/ipc";

/** Presentation-ready engine state for the status pill. */
export interface EngineStatusView {
  status: EngineStatus;
  /** Human label, e.g. "Provisioning…", "Engine ready", or an error message. */
  label: string;
  /** Combined "py3.12 · build123d 0.10.0" version tag, or null while unknown. */
  version: string | null;
  /** Full Python interpreter path the engine resolved, or null while unknown. */
  interpreter: string | null;
  /** Detail/error message from the engine, when present. */
  message: string | null;
  /** 0..1 download fraction while updating the engine; null otherwise. */
  progress: number | null;
}

/** Default label for a given status (when the event carries no message). */
function labelFor(payload: EngineStatusEvent): string {
  switch (payload.status) {
    case "provisioning":
      return "Provisioning…";
    case "updating":
      return "Updating engine";
    case "ready":
      return "Engine ready";
    case "error":
      return payload.message ?? "Engine error";
  }
}

/** Per-tab engine lifecycle, keyed by workspace path (`wsId`). */
export type WorkspaceStatuses = Record<string, EngineStatus>;

/**
 * useWorkspaceStatuses — accumulates each workspace's engine status from the
 * `engine-status` event stream, keyed by the event's `wsId` (the workspace
 * path). Drives the per-tab status dots in {@link WorkspaceSwitcher}.
 *
 * Uses the same `onEngineStatus` listener as {@link useEngineStatus}, but
 * instead of collapsing to a single status it merges each event into a
 * `Record<wsId, status>`. Events without a `wsId` are ignored (they describe
 * the legacy single-engine view, not a specific tab).
 *
 * NOTE: there is no spinner state for an in-progress *build* yet — the only
 * spinner state today is `provisioning` (engine starting). The switcher's
 * `building` pill style is reachable but currently driven only by
 * `provisioning`.
 * TODO: emit a wsId-tagged "build in progress" signal so background-agent
 * builds light the `building` state on their (possibly unfocused) tab.
 */
export function useWorkspaceStatuses(): WorkspaceStatuses {
  const [byWsId, setByWsId] = useState<WorkspaceStatuses>({});

  useEffect(() => {
    let unlisten: (() => void) | undefined;
    let cancelled = false;

    // Seed per-tab dots from all live engines' current status on mount. Engines
    // don't re-emit after a frontend reload, so without this seed the dots stay
    // un-green even though the engines are already ready.
    getEngineStatuses()
      .then((statuses) => {
        if (cancelled) return;
        setByWsId((prev) => {
          const next = { ...prev };
          for (const s of statuses) {
            if (s.wsId) next[s.wsId] = s.status;
          }
          return next;
        });
      })
      .catch(() => {
        // Backend not available — leave the map empty (dots stay idle).
      });

    onEngineStatus((payload) => {
      const wsId = payload.wsId;
      if (!wsId) return; // untagged events don't belong to a specific tab
      setByWsId((prev) =>
        prev[wsId] === payload.status ? prev : { ...prev, [wsId]: payload.status },
      );
    })
      .then((fn) => {
        if (cancelled) fn();
        else unlisten = fn;
      })
      .catch(() => {
        // Backend not available — leave the map empty (dots stay idle).
      });

    return () => {
      cancelled = true;
      unlisten?.();
    };
  }, []);

  return byWsId;
}

export function useEngineStatus(): EngineStatusView {
  // Idle/booting default — the app shows "Provisioning…" until the engine speaks.
  const [view, setView] = useState<EngineStatusView>({
    status: "provisioning",
    label: "Provisioning…",
    version: null,
    interpreter: null,
    message: null,
    progress: null,
  });

  useEffect(() => {
    let unlisten: (() => void) | undefined;
    let cancelled = false;

    const apply = (payload: EngineStatusEvent) =>
      setView({
        status: payload.status,
        label: labelFor(payload),
        version: payload.version,
        interpreter: payload.interpreter,
        message: payload.message,
        progress: payload.progress ?? null,
      });

    // Seed from the current status (covers a missed boot-time "ready" event),
    // then attach the listener for live updates. A live event that lands while
    // the seed query is in flight wins: it's applied after attach, and we only
    // apply the seed if no event has overwritten the view yet.
    let seeded = false;

    getEngineStatus()
      .then((payload) => {
        // Skip the seed if unmounted, the command is unavailable (null), or a
        // live event already updated the view.
        if (cancelled || !payload || seeded) return;
        apply(payload);
      })
      .catch(() => {
        // Older backend without `get_engine_status` — fall back silently.
      });

    onEngineStatus((payload) => {
      seeded = true; // live events take precedence over the mount-time seed
      apply(payload);
    })
      .then((fn) => {
        // If the component unmounted before the listener attached, detach now.
        if (cancelled) fn();
        else unlisten = fn;
      })
      .catch(() => {
        // Backend not available — stay in the idle provisioning state.
      });

    return () => {
      cancelled = true;
      unlisten?.();
    };
  }, []);

  return view;
}
