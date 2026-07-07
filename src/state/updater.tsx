/**
 * UpdaterProvider — a single, app-wide updater instance shared by the top-bar
 * indicator, the startup companion card, and the Settings → Updates panel.
 *
 * This MUST be a provider (not a bare hook) so the auto-check runs exactly once
 * per session and every consumer observes the same status/progress. Separate
 * `useUpdater()` hook instances would each fire their own check (and could each
 * kick off a download), and their states would diverge.
 *
 * When it checks:
 *   • On launch, once per session (as today).
 *   • Every 6 hours on a timer, and on window focus (throttled), so an app left
 *     open for days still learns about a release. All background checks fail
 *     silent — offline or a captive portal never surfaces an error.
 *   • Manually, from Settings.
 * The launch + background checks are gated by the `backgroundUpdateChecks` config
 * flag; the manual check always runs.
 *
 * What it does with an available update follows `updateBehavior`:
 *   • notify       → surface the "Update available" indicator + companion card.
 *   • autoDownload → download + install now, then offer a restart.
 *   • silent       → download + install in the background and stay quiet; the
 *                    update applies on the next launch (no restart prompt).
 *
 * Progress streams over the Rust `updater://progress` event.
 *
 * Dev note: a real check is disabled in dev (a dev build has no signed installer
 * to apply), but a `?mockUpdate` flag routes every check/download through
 * {@link readMockUpdateConfig}/{@link simulateMockDownload} so the whole flow is
 * exercisable in `tauri dev`. That path is dead-code-eliminated from production.
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

import { useAppConfig } from "./appConfig";
import { checkForUpdate, downloadAndInstall, relaunchForUpdate } from "../lib/ipc/config";
import { useAppVersion } from "../hooks/useAppVersion";
import { logError } from "../lib/logger";
import {
  nextActionFor,
  shouldRunPeriodicCheck,
  PERIODIC_CHECK_INTERVAL_MS,
  FOCUS_CHECK_THROTTLE_MS,
  type UpdateAction,
  type UpdateStatus,
  type UseUpdaterResult,
} from "../hooks/useUpdater";
import {
  readMockUpdateConfig,
  simulateMockDownload,
  mockUpdateNotes,
  nextMockVersion,
  type MockUpdateConfig,
} from "../lib/devMockUpdater";

const UpdaterContext = createContext<UseUpdaterResult | null>(null);

/** The result of a check, from the real backend or the dev mock. */
interface CheckResult {
  available: boolean;
  version: string | null;
  notes: string | null;
  error: string | null;
}

export function UpdaterProvider({ children }: { children: ReactNode }) {
  const { config, loading } = useAppConfig();
  const { updateBehavior, backgroundUpdateChecks } = config;
  const current = useAppVersion();

  const [status, setStatus] = useState<UpdateStatus>("idle");
  const [version, setVersion] = useState<string | null>(null);
  const [notes, setNotes] = useState<string | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastCheckedAt, setLastCheckedAt] = useState<number | null>(null);
  const [dismissed, setDismissed] = useState(false);

  const checkedOnce = useRef(false);
  const mounted = useRef(true);
  // The dev mock config (null in production / when not enabled), read once.
  const mock = useRef<MockUpdateConfig | null>(readMockUpdateConfig());
  // Live values read inside async callbacks / listeners without re-binding them.
  const channelRef = useRef(config.updateChannel);
  channelRef.current = config.updateChannel;
  // The running version, so the dev mock can offer one patch above it.
  const currentVersionRef = useRef(current);
  currentVersionRef.current = current;
  const behaviorRef = useRef(updateBehavior);
  behaviorRef.current = updateBehavior;
  const statusRef = useRef(status);
  statusRef.current = status;
  const lastCheckedRef = useRef(lastCheckedAt);
  lastCheckedRef.current = lastCheckedAt;
  // The version we last surfaced a card for, so a periodic re-check of the same
  // release doesn't re-pop a card the user already dismissed.
  const notifiedVersion = useRef<string | null>(null);
  // True while a manual check is in flight, so a background check that lands at the
  // same moment can't auto-download behind the user's "just checking" action.
  const manualCheckInFlight = useRef(false);

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

  // Surface an available update. A new version always shows the card; a re-check
  // of the same version respects a prior dismissal.
  const showAvailable = useCallback((v: string | null) => {
    if (v !== notifiedVersion.current) {
      notifiedVersion.current = v;
      setDismissed(false);
    }
    setStatus("available");
  }, []);

  // One check, from the real backend or the dev mock. Never throws.
  const performCheck = useCallback(async (): Promise<CheckResult> => {
    const m = mock.current;
    // A short beat so the check "moment" is visible, like a real network hop.
    const beat = () => new Promise((r) => setTimeout(r, 450));
    // An explicit ?mockUpdate scenario picks the version; otherwise, in dev, we
    // still simulate an available update so "Check now" exercises the whole update
    // UI with no flag needed (a dev build has no signed release to find, so a real
    // check can only ever come back empty). Production never takes either path.
    if (m || import.meta.env.DEV) {
      await beat();
      const version = m?.version ?? nextMockVersion(currentVersionRef.current);
      return { available: true, version, notes: mockUpdateNotes(), error: null };
    }
    try {
      const res = await checkForUpdate(channelRef.current);
      return { ...res, notes: res.notes ?? null, error: null };
    } catch (e) {
      const message =
        e instanceof Error ? e.message : typeof e === "string" ? e : "Update check failed.";
      return { available: false, version: null, notes: null, error: message };
    }
  }, []);

  // Shared download+install. `silent` keeps the user uninterrupted: on success it
  // returns to `idle` (no "Restart to update" prompt) so the update simply applies
  // on the next launch. notify/autoDownload end at `ready` and surface a restart.
  const runDownload = useCallback(async (silent: boolean) => {
    setError(null);
    setProgress(0);
    // Silent installs must not raise the companion card; the header pill still
    // reflects progress for anyone who looks.
    if (silent) setDismissed(true);
    setStatus("downloading");
    try {
      // The dev build has no signed installer to apply, so a real download+install
      // would either error or (worse) restart the running dev app. Always simulate
      // in dev; only a production build touches the real updater.
      if (import.meta.env.DEV) {
        await simulateMockDownload(
          setProgress,
          () => mounted.current,
          mock.current?.scenario === "error",
        );
      } else {
        await downloadAndInstall(channelRef.current);
      }
      if (!mounted.current) return;
      setProgress(1);
      if (silent) {
        setStatus("idle");
      } else {
        setDismissed(false); // the "ready" moment always deserves the card
        setStatus("ready");
      }
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
      setDismissed(false);
      setError(message);
      setStatus("error");
    }
  }, []);

  // Decide what to do with an available update. Honors an explicit mock scenario,
  // otherwise follows the user's update-behavior.
  const actOnAvailable = useCallback(
    (res: CheckResult) => {
      setVersion(res.version);
      setNotes(res.notes);

      const m = mock.current;
      if (m && m.scenario === "ready") {
        setProgress(1);
        setDismissed(false);
        setStatus("ready");
        return;
      }
      const action: UpdateAction =
        m && m.scenario !== "behavior"
          ? m.scenario === "available"
            ? "show-indicator"
            : m.scenario === "silent"
              ? "download-silent"
              : "download" // "download" and "error" both start a download
          : nextActionFor(behaviorRef.current, res.available);

      switch (action) {
        case "show-indicator":
          showAvailable(res.version);
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
    },
    [runDownload, showAvailable],
  );

  // A silent background check (launch / timer / focus). Never sets "checking",
  // never surfaces a check error, and won't disturb an in-flight download.
  const runBackgroundCheck = useCallback(async () => {
    const s = statusRef.current;
    if (s === "downloading" || s === "ready") return; // already handling an update
    if (manualCheckInFlight.current) return; // don't auto-download under a manual check
    const res = await performCheck();
    if (!mounted.current) return;
    setLastCheckedAt(Date.now());
    if (res.error) {
      logError("update background check failed", res.error);
      return;
    }
    if (res.available) actOnAvailable(res);
  }, [performCheck, actOnAvailable]);

  // Auto-check once per session on launch, after config settles.
  useEffect(() => {
    if (loading || checkedOnce.current) return;
    // Real updater is production-only; in dev only the mock drives it.
    if (import.meta.env.DEV && !mock.current) return;
    if (!backgroundUpdateChecks) return; // user turned automatic checks off
    checkedOnce.current = true;
    void runBackgroundCheck();
  }, [loading, backgroundUpdateChecks, runBackgroundCheck]);

  // Periodic timer + throttled window-focus re-checks.
  useEffect(() => {
    if (loading) return;
    if (import.meta.env.DEV && !mock.current) return;
    if (!backgroundUpdateChecks) return;

    const maybeCheck = (throttleMs: number) => {
      if (!shouldRunPeriodicCheck(lastCheckedRef.current, Date.now(), throttleMs)) return;
      void runBackgroundCheck();
    };
    const timer = window.setInterval(() => maybeCheck(0), PERIODIC_CHECK_INTERVAL_MS);
    const onFocus = () => maybeCheck(FOCUS_CHECK_THROTTLE_MS);
    window.addEventListener("focus", onFocus);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", onFocus);
    };
  }, [loading, backgroundUpdateChecks, runBackgroundCheck]);

  // Indicator/card "Install" (notify flow) always wants the restart prompt at the end.
  const startDownload = useCallback(() => {
    void runDownload(false);
  }, [runDownload]);

  const restart = useCallback(() => {
    // Never relaunch the dev app: there's no installed update to apply, and killing
    // `tauri dev` just closes the window. Reset so the flow stays replayable.
    if (import.meta.env.DEV) {
      console.info("[updater] restart requested; a production build would relaunch here.");
      setStatus("idle");
      setProgress(null);
      setDismissed(false);
      notifiedVersion.current = null;
      return;
    }
    // Single-instance-safe relaunch (waits for this process to exit and release
    // the lock before starting the new instance). Surface a failure instead of
    // leaving the user on a dead "Restart" click.
    void relaunchForUpdate().catch((e) => {
      if (!mounted.current) return;
      setError(e instanceof Error ? e.message : "Couldn't restart to apply the update.");
      setStatus("error");
    });
  }, []);

  const dismiss = useCallback(() => setDismissed(true), []);

  const checkNow = useCallback(async () => {
    // Held for the whole call so a concurrent background check can't auto-download.
    manualCheckInFlight.current = true;
    try {
      setError(null);
      // Show "checking" unless we'd stomp an in-flight/finished download.
      setStatus((s) => (s === "downloading" || s === "ready" ? s : "checking"));
      const res = await performCheck();
      if (!mounted.current) return { available: false, version: null, error: "unmounted" };
      setLastCheckedAt(Date.now());
      if (res.error) {
        // No status change beyond leaving "checking": the Settings panel shows the
        // returned error inline; the top-bar "Update failed" pill is for downloads.
        setError(res.error);
        setStatus((s) => (s === "checking" ? "idle" : s));
        return { available: false, version: null, error: res.error };
      }
      setVersion(res.version);
      setNotes(res.notes);
      // A manual check reveals the indicator but never auto-downloads, even under
      // autoDownload/silent — the user asked to look, not to install.
      setStatus((s) => {
        if (s === "downloading" || s === "ready") return s;
        if (res.available) {
          if (res.version !== notifiedVersion.current) {
            notifiedVersion.current = res.version;
            setDismissed(false);
          }
          return "available";
        }
        return "idle";
      });
      return { available: res.available, version: res.version, error: null };
    } finally {
      manualCheckInFlight.current = false;
    }
  }, [performCheck]);

  // Memoize so consumers don't re-render on every provider render (the callbacks
  // are already stable via useCallback).
  const value = useMemo(
    () => ({
      status,
      version,
      notes,
      progress,
      error,
      lastCheckedAt,
      dismissed,
      startDownload,
      restart,
      dismiss,
      checkNow,
    }),
    [
      status,
      version,
      notes,
      progress,
      error,
      lastCheckedAt,
      dismissed,
      startDownload,
      restart,
      dismiss,
      checkNow,
    ],
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
