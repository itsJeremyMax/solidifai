import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { invoke } from "./core";

/* ─────────────────────────────── reference library ────────────────────────────── */

/** A single reference part entry (seed or user-added). */
export interface ReferenceEntry {
  id: string;
  category: string;
  dims_mm: Record<string, number | number[]>;
  source: string;
  aliases?: string[];
  mounting_holes?: Record<string, unknown>;
  notes?: string;
  origin?: "learned" | "manual";
  verified_at?: string;
  verified_in?: string;
}

/** The full reference library split into seed (built-in) and user entries. */
export interface ReferenceLibrary {
  seed: ReferenceEntry[];
  user: ReferenceEntry[];
}

/** Read the full reference library (seed + user entries). Re-throws on failure. */
export async function getReferenceLibrary(): Promise<ReferenceLibrary> {
  return invoke("get_reference_library");
}

/**
 * Persist a new or updated reference entry (stamps `origin: "manual"` server-side).
 * Re-throws on failure so the caller can surface the error.
 */
export async function saveReferenceEntry(entry: ReferenceEntry): Promise<unknown> {
  return invoke("save_reference_entry", { entry });
}

/**
 * Delete the user reference entry with the given `id`.
 * Re-throws on failure so the caller can surface the error.
 */
export async function deleteReferenceEntry(id: string): Promise<unknown> {
  return invoke("delete_reference_entry", { id });
}

/**
 * Subscribe to reference-library change notifications (any write via GUI or Sol).
 * Returns an unlisten function.
 */
export async function onReferenceLibraryUpdated(handler: () => void): Promise<UnlistenFn> {
  return listen("reference-library-updated", () => handler());
}
