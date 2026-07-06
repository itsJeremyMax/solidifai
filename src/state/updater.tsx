/**
 * UpdaterProvider — a single, app-wide updater instance shared by the top-bar
 * indicator and the Settings → Updates panel.
 *
 * This MUST be a provider (not a bare hook) so the auto-check runs exactly once
 * per session and both consumers observe the same status/progress. Two separate
 * `useUpdater()` hook instances would each fire their own check (and could each
 * kick off a download), and their states would diverge.
 *
 * On mount (after the app-config loads) it checks the configured channel and
 * acts on `updateBehavior`:
 *   • notify       → surface the "Update available" indicator.
 *   • autoDownload → download + install now, then offer a restart.
 *   • silent       → download + install in the background and stay quiet; the
 *                    update applies on the next launch (no restart prompt).
 *
 * Progress streams over the Rust `updater://progress` event; the listener is
 * cleaned up on unmount.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { listen } from "@tauri-apps/api/event";
import { relaunch } from "@tauri-apps/plugin-process";

import { useAppConfig } from "./appConfig";
import { checkForUpdate, downloadAndInstall } from "../lib/ipc";
import { logError } from "../lib/logger";
import { nextActionFor, type UpdateStatus, type UseUpdaterResult } from "../hooks/useUpdater";

const UpdaterContext = createContext<UseUpdaterResult | null>(null);

export function UpdaterProvider({ children }: { children: ReactNode }) {
  const { config, loading } = useAppConfig();
  const { updateBehavior } = config;

  const [status, setStatus] = useState<UpdateStatus>("idle");
  const [version, setVersion] = useState<string | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const checkedOnce = useRef(false);
  const mounted = useRef(true);
  // Read the live channel inside async callbacks without re-binding them.
  const channelRef = useRef(config.updateChannel);
  channelRef.current = config.updateChannel;

  useEffect(() => {
    mounted.current = true;
    const unlisten = listen<{ downloaded: number; total: number | null }>(
      "updater://progress",
      (event) => {
        if (!mounted.current) return;
        const { downloaded, total } = event.payload;
        setProgress(total && total > 0 ? Math.min(1, downloaded / total) : null);
      },
    );
    return () => {
      mounted.current = false;
      void unlisten.then((off) => off());
    };
  }, []);

  // Shared download+install. `silent` keeps the user uninterrupted: on success it
  // returns to `idle` (no "Restart to update" prompt) so the update simply applies
  // on the next launch. notify/autoDownload end at `ready` and surface a restart.
  const runDownload = useCallback(async (silent: boolean) => {
    setError(null);
    setProgress(0);
    setStatus("downloading");
    try {
      await downloadAndInstall(channelRef.current);
      if (!mounted.current) return;
      setProgress(1);
      setStatus(silent ? "idle" : "ready");
    } catch (e) {
      if (!mounted.current) return;
      const message =
        e instanceof Error ? e.message : typeof e === "string" ? e : "Update download failed.";
      // A retry after the release was pulled (or a stale indicator): nothing to
      // download is not a failure, so clear the pill instead of looping "error".
      if (message.includes("no update available")) {
        setProgress(null);
        setStatus("idle");
        return;
      }
      setError(message);
      setStatus("error");
    }
  }, []);

  // Auto-check once per session, only after config has loaded.
  useEffect(() => {
    // A dev build has no signed installer to apply, so the check can only ever
    // error (and would flash "Update failed" in the bar). The updater is a
    // production-only concern, so skip the auto-check entirely in dev.
    if (import.meta.env.DEV || loading || checkedOnce.current) return;
    checkedOnce.current = true;

    void (async () => {
      let res: { available: boolean; version: string | null };
      try {
        res = await checkForUpdate(channelRef.current);
      } catch (e) {
        // A failed launch check (offline, captive portal, DNS) is routine for a
        // desktop app: log it and stay idle. The red "Update failed" pill is
        // reserved for failures of an actual download.
        logError("update auto-check failed", e);
        return;
      }
      if (!mounted.current) return;
      setVersion(res.version);

      switch (nextActionFor(updateBehavior, res.available)) {
        case "show-indicator":
          setStatus("available");
          break;
        case "download":
          void runDownload(false);
          break;
        case "download-silent":
          void runDownload(true);
          break;
        case "idle":
          break;
      }
    })();
  }, [loading, updateBehavior, runDownload]);

  // Indicator "Download" (notify flow) always wants the restart prompt at the end.
  const startDownload = useCallback(() => {
    void runDownload(false);
  }, [runDownload]);

  const restart = useCallback(() => {
    void relaunch();
  }, []);

  const checkNow = useCallback(async () => {
    setError(null);
    try {
      const res = await checkForUpdate(channelRef.current);
      if (mounted.current) {
        setVersion(res.version);
        // Reveal the indicator on a manual hit too, unless we're mid/post download.
        setStatus((s) =>
          s === "downloading" || s === "ready" ? s : res.available ? "available" : "idle",
        );
      }
      return { ...res, error: null };
    } catch (e) {
      const message =
        e instanceof Error ? e.message : typeof e === "string" ? e : "Update check failed.";
      // No status change: the Settings panel shows the returned error inline,
      // and the top-bar "Update failed" pill is for download failures only.
      if (mounted.current) setError(message);
      // The caller must be able to tell a failed check from "up to date".
      return { available: false, version: null, error: message };
    }
  }, []);

  // Memoize so consumers don't re-render on every provider render (the three
  // callbacks are already stable via useCallback).
  const value = useMemo(
    () => ({ status, version, progress, error, startDownload, restart, checkNow }),
    [status, version, progress, error, startDownload, restart, checkNow],
  );

  return <UpdaterContext.Provider value={value}>{children}</UpdaterContext.Provider>;
}

/** Access the shared updater state. Throws if used outside {@link UpdaterProvider}. */
// Provider + its hook live together by convention; only costs the file's fast refresh.
// eslint-disable-next-line react-refresh/only-export-components
export function useUpdater(): UseUpdaterResult {
  const ctx = useContext(UpdaterContext);
  if (ctx === null) {
    throw new Error("useUpdater must be used within <UpdaterProvider>");
  }
  return ctx;
}
