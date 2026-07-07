import type { ReferenceEntry } from "../../lib/ipc/references";
import type { ReferenceRow } from "../../hooks/useReferences";

/**
 * Data the References list shares with its editor route (`new` / `:entryId`)
 * via Outlet context. The list owns the merged entry set (seed + user) and the
 * persistence calls; the editor owns only the in-progress form and writes a
 * single entry back through `save` (or removes one through `remove`).
 */
export interface ReferencesOutletContext {
  entries: ReferenceRow[];
  /** Persist a new or edited entry. Re-throws Rust validation errors. */
  save: (entry: ReferenceEntry) => Promise<void>;
  /** Delete a user entry by id. Re-throws on failure. */
  remove: (id: string) => Promise<void>;
}
