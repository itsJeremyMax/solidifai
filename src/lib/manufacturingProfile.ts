import { invoke } from "@tauri-apps/api/core";

/** The resolved profile is an open numeric/string object keyed by section. */
export type ProfileValues = Record<string, Record<string, number | string>>;

export interface ProfileView {
  resolved: ProfileValues;
  overrides: ProfileValues;
  /** Present only in workspace scope, for attributing inherited values. */
  globalOverrides?: ProfileValues;
  material: { id: string; label: string };
}

const EMPTY: ProfileView = { resolved: {}, overrides: {}, material: { id: "", label: "" } };

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
