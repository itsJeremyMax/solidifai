/**
 * useMaterials — owns a material library for one scope ("global" | "workspace")
 * and exposes invariant-safe mutations.
 *
 * Every mutation is optimistic: it applies the change locally first (so the UI
 * is instant), persists the whole library through `src/lib/materials.ts`, then
 * adopts the backend's authoritative copy (the backend re-enforces invariants,
 * e.g. a non-null default, so the adopted copy is the source of truth). If the
 * write fails, the optimistic change is reverted by re-reading the persisted
 * library and an error message is surfaced.
 */
import { useCallback, useEffect, useState } from "react";
import {
  getGlobalMaterials,
  setGlobalMaterials,
  getWorkspaceMaterials,
  setWorkspaceMaterials,
  type Material,
  type MaterialLibrary,
} from "../lib/materials";

export type Scope = "global" | "workspace";

/* ── pure library transforms (exported for unit tests; no React, no IPC) ──── */

/** Insert `m`, or replace the existing entry with the same id, preserving order. */
export function applyUpsert(library: MaterialLibrary, m: Material): MaterialLibrary {
  const materials = library.materials.some((x) => x.id === m.id)
    ? library.materials.map((x) => (x.id === m.id ? m : x))
    : [...library.materials, m];
  return { ...library, materials };
}

/** Drop the entry with `id` (no-op if absent). Does not touch `default`. */
export function applyRemove(library: MaterialLibrary, id: string): MaterialLibrary {
  return { ...library, materials: library.materials.filter((m) => m.id !== id) };
}

/** Set the default id. The backend re-validates that it points at a real entry. */
export function applySetDefault(library: MaterialLibrary, id: string): MaterialLibrary {
  return { ...library, default: id };
}

export function useMaterials(scope: Scope) {
  const [library, setLibrary] = useState<MaterialLibrary>({ default: null, materials: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Memoized on scope so the effect/commit deps below are stable until scope flips.
  const read = useCallback(
    () => (scope === "global" ? getGlobalMaterials() : getWorkspaceMaterials()),
    [scope],
  );
  const write = useCallback(
    (lib: MaterialLibrary) =>
      scope === "global" ? setGlobalMaterials(lib) : setWorkspaceMaterials(lib),
    [scope],
  );

  useEffect(() => {
    let live = true;
    setLoading(true);
    read().then((lib) => {
      if (live) {
        setLibrary(lib);
        setLoading(false);
      }
    });
    return () => {
      live = false;
    };
  }, [read]);

  // Persist a new library; adopt the backend's authoritative copy or surface error.
  const commit = useCallback(
    async (next: MaterialLibrary) => {
      setLibrary(next); // optimistic
      try {
        setLibrary(await write(next));
        setError(null);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Could not save materials");
        setLibrary(await read()); // revert to truth
      }
    },
    [read, write],
  );

  const upsert = useCallback((m: Material) => commit(applyUpsert(library, m)), [library, commit]);

  const remove = useCallback((id: string) => commit(applyRemove(library, id)), [library, commit]);

  const setDefault = useCallback(
    (id: string) => commit(applySetDefault(library, id)),
    [library, commit],
  );

  return { library, loading, error, upsert, remove, setDefault };
}
