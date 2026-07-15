import { invoke } from "@tauri-apps/api/core";
import catalog from "../../engine/solidifai_engine/manufacturing_catalog.json";

/** A material in the global or workspace library (mirrors Rust `Material`). */
export interface Material {
  id: string;
  label: string;
  base: string;
  colorHex: string;
  finish: "matte" | "satin" | "gloss" | "metallic";
  /** Optional; derived from a known base when absent. */
  process?: ManufacturingProcess;
}

export type ManufacturingProcess = string;
export const CATALOG = catalog;

/** A material library: an ordered set plus the chosen default id. */
export interface MaterialLibrary {
  /** Default material id; null in a workspace means "inherit the global default". */
  default: string | null;
  materials: Material[];
}

const EMPTY: MaterialLibrary = { default: null, materials: [] };

function toLibrary(v: unknown): MaterialLibrary {
  if (typeof v !== "object" || v === null) return EMPTY;
  const r = v as Record<string, unknown>;
  const materials = Array.isArray(r.materials) ? (r.materials as Material[]) : [];
  return { default: typeof r.default === "string" ? r.default : null, materials };
}

/** Read the global library (the backend seeds it on first run). */
export async function getGlobalMaterials(): Promise<MaterialLibrary> {
  try {
    return toLibrary(await invoke<unknown>("get_global_materials"));
  } catch {
    return EMPTY;
  }
}

/** Persist the whole global library; returns the backend's authoritative copy. */
export async function setGlobalMaterials(library: MaterialLibrary): Promise<MaterialLibrary> {
  return toLibrary(await invoke<unknown>("set_global_materials", { library }));
}

/** Read the active workspace's library (empty if no workspace / no file). */
export async function getWorkspaceMaterials(): Promise<MaterialLibrary> {
  try {
    return toLibrary(await invoke<unknown>("get_workspace_materials"));
  } catch {
    return EMPTY;
  }
}

/** Persist the active workspace's library. */
export async function setWorkspaceMaterials(library: MaterialLibrary): Promise<MaterialLibrary> {
  return toLibrary(await invoke<unknown>("set_workspace_materials", { library }));
}

/** Derive the manufacturing process from a base substance (UI mirror of the Rust/engine rule). */
export function processForBase(base: string): ManufacturingProcess | undefined {
  return CATALOG.bases[base as keyof typeof CATALOG.bases]?.defaultProcess;
}

export function supportedProcesses(): ManufacturingProcess[] {
  return Object.keys(CATALOG.processes);
}

export function profileSettings(process: ManufacturingProcess): string[] {
  return CATALOG.processes[process as keyof typeof CATALOG.processes]?.profileSettings ?? [];
}
