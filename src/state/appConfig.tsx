/**
 * appConfig — the app's first shared store: global viewport feature flags,
 * persisted via the Tauri app-config commands.
 *
 * Deliberately minimal. The provider loads the config once on mount, then
 * exposes the current `config` plus a `setFlag(key, value)` that updates
 * OPTIMISTICALLY (so toggles feel instant), persists the single-key patch via
 * `setAppConfig`, and adopts the backend's authoritative merged result. On a
 * persist failure it REVERTS the optimistic value and surfaces a transient error
 * string (`error`) so the settings UI can flash it without leaving the toggle in
 * a lying state.
 *
 * The provider is mounted above the whole view switch (App.tsx) so the config
 * survives navigation between the launcher, editor, and settings, and is read by
 * BOTH the settings page (to render toggles) and the editor scene (to apply them
 * — see Viewport.tsx).
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

import { getAppConfig, setAppConfig, DEFAULT_APP_CONFIG, type AppConfig } from "../lib/ipc";

interface AppConfigContextValue {
  /** The current flags. Starts at the shipped defaults until the load resolves. */
  config: AppConfig;
  /** True until the initial `getAppConfig` resolves (lets the UI show a quiet load state). */
  loading: boolean;
  /** Last persist error (transient; cleared on the next successful `setFlag`), or null. */
  error: string | null;
  /**
   * Set one flag: optimistic local update + persisted single-key patch. Reverts
   * the optimistic value and sets `error` if the backend write fails.
   */
  setFlag: <K extends keyof AppConfig>(key: K, value: AppConfig[K]) => void;
}

const AppConfigContext = createContext<AppConfigContextValue | null>(null);

export function AppConfigProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<AppConfig>(DEFAULT_APP_CONFIG);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Guards against a stale setState after unmount during the in-flight load.
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    getAppConfig().then((c) => {
      if (!mounted.current) return;
      setConfig(c);
      setLoading(false);
    });
    return () => {
      mounted.current = false;
    };
  }, []);

  const setFlag = useCallback(<K extends keyof AppConfig>(key: K, value: AppConfig[K]) => {
    setError(null);
    // Snapshot the prior value so we can revert on failure.
    let prev: AppConfig[K] | undefined;
    setConfig((c) => {
      prev = c[key];
      return { ...c, [key]: value };
    });
    void setAppConfig({ [key]: value } as Partial<AppConfig>)
      .then((merged) => {
        if (mounted.current) setConfig(merged); // adopt backend truth
      })
      .catch((e) => {
        if (!mounted.current) return;
        // Revert the optimistic flip and surface the error.
        setConfig((c) => ({ ...c, [key]: prev as AppConfig[K] }));
        setError(e instanceof Error ? e.message : "Failed to save setting");
      });
  }, []);

  // Memoize so consumers don't re-render on every provider render (setFlag is
  // already stable via useCallback).
  const value = useMemo(
    () => ({ config, loading, error, setFlag }),
    [config, loading, error, setFlag],
  );

  return <AppConfigContext.Provider value={value}>{children}</AppConfigContext.Provider>;
}

/** Access the app-config store. Throws if used outside {@link AppConfigProvider}. */
// Provider + its hook live together by convention; only costs the file's fast refresh.
// eslint-disable-next-line react-refresh/only-export-components
export function useAppConfig(): AppConfigContextValue {
  const ctx = useContext(AppConfigContext);
  if (ctx === null) {
    throw new Error("useAppConfig must be used within <AppConfigProvider>");
  }
  return ctx;
}
