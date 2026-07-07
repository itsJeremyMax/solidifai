import { invoke } from "@tauri-apps/api/core";

/**
 * Custom instructions — free-text guidance woven into a workspace's AGENTS.md.
 * Two additive layers, mirroring the manufacturing profile: a GLOBAL layer
 * applied to every workspace, and a PER-WORKSPACE layer for the focused one. Rust
 * is the sole writer of AGENTS.md; both layers are appended on the next provision
 * (workspace open). Reads never throw (empty on failure); writes re-throw.
 */
export type InstructionScope = "global" | "workspace";

export async function getCustomInstructions(scope: InstructionScope): Promise<string> {
  const cmd =
    scope === "global" ? "get_global_custom_instructions" : "get_workspace_custom_instructions";
  try {
    return (await invoke<string>(cmd)) ?? "";
  } catch {
    return "";
  }
}

export async function setCustomInstructions(scope: InstructionScope, text: string): Promise<void> {
  const cmd =
    scope === "global" ? "set_global_custom_instructions" : "set_workspace_custom_instructions";
  await invoke(cmd, { text });
}
