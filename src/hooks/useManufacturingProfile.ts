import { useCallback, useEffect, useState } from "react";
import {
  getGlobalProfile,
  setGlobalProfile,
  getWorkspaceProfile,
  setWorkspaceProfile,
  type ProfileView,
  type ProfileValues,
} from "../lib/manufacturingProfile";

export type Scope = "global" | "workspace";

const EMPTY: ProfileView = { resolved: {}, overrides: {}, material: { id: "", label: "" } };

export function useManufacturingProfile(scope: Scope) {
  const [view, setView] = useState<ProfileView>(EMPTY);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Memoized on scope so the effect/commit deps below are stable until scope flips.
  const read = useCallback(
    () => (scope === "global" ? getGlobalProfile() : getWorkspaceProfile()),
    [scope],
  );
  const write = useCallback(
    (set: ProfileValues, unset: string[]) =>
      scope === "global" ? setGlobalProfile(set, unset) : setWorkspaceProfile(set, unset),
    [scope],
  );

  useEffect(() => {
    let live = true;
    setLoading(true);
    read().then((v) => {
      if (live) {
        setView(v);
        setLoading(false);
      }
    });
    return () => {
      live = false;
    };
  }, [read]);

  // Send the change; on success adopt the backend's returned view as truth (so resolved
  // values stay authoritative). On failure revert to the pre-commit view and surface the
  // error — no optimistic update is applied before the await.
  const commit = useCallback(
    async (set: ProfileValues, unset: string[]) => {
      const prev = view;
      try {
        setView(await write(set, unset));
        setError(null);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Could not save the profile");
        setView(prev); // revert to the pre-commit view
      }
    },
    [view, write],
  );

  const setField = useCallback(
    (section: string, key: string, value: number | string) =>
      commit({ [section]: { [key]: value } }, []),
    [commit],
  );

  const resetField = useCallback(
    (section: string, key: string) => commit({}, [`${section}.${key}`]),
    [commit],
  );

  const setProcessSetting = useCallback(
    (key: string, value: number | string) =>
      commit(
        { process: { id: String(view.resolved.process?.id ?? "fdm"), settings: { [key]: value } } },
        [],
      ),
    [commit, view],
  );
  const resetProcessSetting = useCallback(
    (key: string) => commit({}, [`process.settings.${key}`]),
    [commit],
  );

  return { view, loading, error, setField, resetField, setProcessSetting, resetProcessSetting };
}
