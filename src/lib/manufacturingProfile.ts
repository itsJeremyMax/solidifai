import { invoke } from "@tauri-apps/api/core";
import { profileSettings } from "./materials";

export type ProcessId = "fdm" | "sla" | "sls" | "cnc" | "injection" | string;
export interface ProcessProfile {
  id: ProcessId;
  settings: Record<string, number | string>;
}
/** The resolved profile is an open object keyed by section, with a v2 process envelope. */
export type ProfileValues = Record<string, unknown> & { process?: ProcessProfile };

export interface ProfileView {
  resolved: ProfileValues;
  overrides: ProfileValues;
  /** Present only in workspace scope, for attributing inherited values. */
  globalOverrides?: ProfileValues;
  material: { id: string; label: string };
}

const EMPTY: ProfileView = { resolved: {}, overrides: {}, material: { id: "", label: "" } };

/** Settings safe to surface for a process, as declared by the shared catalog. */
export function processSettings(process: ProcessProfile): Record<string, number | string> {
  const allowed = new Set(profileSettings(process.id));
  return Object.fromEntries(Object.entries(process.settings).filter(([key]) => allowed.has(key)));
}

export async function getGlobalProfile(): Promise<ProfileView> {
  try {
    return (await invoke<ProfileView>("get_global_manufacturing_profile")) ?? EMPTY;
  } catch {
    return EMPTY;
  }
}
export async function setGlobalProfile(set: ProfileValues, unset: string[]): Promise<ProfileView> {
  return invoke<ProfileView>("set_global_manufacturing_profile", { set, unset });
}
export async function getWorkspaceProfile(): Promise<ProfileView> {
  try {
    return (await invoke<ProfileView>("get_workspace_manufacturing_profile")) ?? EMPTY;
  } catch {
    return EMPTY;
  }
}
export async function setWorkspaceProfile(
  set: ProfileValues,
  unset: string[],
): Promise<ProfileView> {
  return invoke<ProfileView>("set_workspace_manufacturing_profile", { set, unset });
}
