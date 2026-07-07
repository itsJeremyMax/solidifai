import { useCallback, useEffect, useState } from "react";
import {
  deleteReferenceEntry,
  getReferenceLibrary,
  onReferenceLibraryUpdated,
  saveReferenceEntry,
  type ReferenceEntry,
} from "../lib/ipc/references";

/** A reference entry augmented with merge-layer flags for UI presentation. */
export interface ReferenceRow extends ReferenceEntry {
  /** True when the entry comes from the seed and has no user override. */
  builtin: boolean;
  /** True when this user entry overrides a seed entry with the same id. */
  shadowsSeed: boolean;
}

/**
 * Load the reference library (seed + user), merge them, and keep in sync via the
 * `reference-library-updated` event. User entries shadow seed entries that share
 * the same id. Results are sorted alphabetically by id.
 */
export function useReferences() {
  const [entries, setEntries] = useState<ReferenceRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const lib = await getReferenceLibrary();
      const userIds = new Set(lib.user.map((e) => e.id));
      const seedIds = new Set(lib.seed.map((e) => e.id));
      const rows: ReferenceRow[] = [
        ...lib.user.map((e) => ({ ...e, builtin: false, shadowsSeed: seedIds.has(e.id) })),
        ...lib.seed
          .filter((e) => !userIds.has(e.id))
          .map((e) => ({ ...e, builtin: true, shadowsSeed: false })),
      ].sort((a, b) => a.id.localeCompare(b.id));
      setEntries(rows);
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }, []);

  useEffect(() => {
    void load();
    // cancelled guard: tear down even when unmount beats the listen() promise.
    let cancelled = false;
    let unlisten: (() => void) | undefined;
    void onReferenceLibraryUpdated(() => void load()).then((u) => {
      if (cancelled) u();
      else unlisten = u;
    });
    return () => {
      cancelled = true;
      unlisten?.();
    };
  }, [load]);

  /** Save (add or update) a reference entry and reload. */
  const save = useCallback(
    async (entry: ReferenceEntry) => {
      await saveReferenceEntry(entry);
      await load();
    },
    [load],
  );

  /** Delete a reference entry by id and reload. */
  const remove = useCallback(
    async (id: string) => {
      await deleteReferenceEntry(id);
      await load();
    },
    [load],
  );

  return { entries, error, save, remove, reload: load };
}
