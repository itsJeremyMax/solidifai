import { engineCall, invoke } from "./core";

/* ───────────────────────────── history ────────────────────────────────── */

/** One entry in the workspace edit history (a git commit). */
export interface HistoryEntry {
  index: number;
  sha: string;
  message: string;
  /** Commit time, epoch seconds. */
  time: number;
  /** True for the entry currently shown in the viewport. */
  current: boolean;
}

/** The engine's `history` response: ordered entries + the current index. */
export interface HistoryState {
  entries: HistoryEntry[];
  index: number;
}

/** Read the workspace edit history, or `null` if the engine isn't ready. */
export async function engineHistory(): Promise<HistoryState | null> {
  try {
    return JSON.parse(await invoke<string>("engine_history")) as HistoryState;
  } catch {
    return null;
  }
}

/** Undo the last edit. Returns the raw engine response, or `null` if unavailable. */
export async function engineUndo(): Promise<string | null> {
  return engineCall<string>("engine_undo");
}

/** Redo the last undone edit. Returns the raw response, or `null` if unavailable. */
export async function engineRedo(): Promise<string | null> {
  return engineCall<string>("engine_redo");
}

/** Jump to history entry `index`. Returns the raw response, or `null` if unavailable. */
export async function engineGoto(index: number): Promise<string | null> {
  return engineCall<string>("engine_goto", { index });
}
