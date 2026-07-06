/**
 * Open-tabs persistence for restore-on-launch. Mirrors lastRoute.ts — pure UI
 * state in localStorage, reads guarded, writes best-effort.
 */
const KEY = "solidifai.openTabs";

export interface OpenTabsState {
  open: string[];
  focused: string | null;
}

export function saveOpenTabs(state: OpenTabsState): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(state));
  } catch {
    /* best-effort */
  }
}

export function readOpenTabs(): OpenTabsState | null {
  try {
    const v = localStorage.getItem(KEY);
    if (!v) return null;
    const parsed = JSON.parse(v) as unknown;
    if (
      typeof parsed !== "object" ||
      parsed === null ||
      !Array.isArray((parsed as Record<string, unknown>).open)
    ) {
      return null;
    }
    const p = parsed as Record<string, unknown>;
    const open = (p.open as unknown[]).filter((x): x is string => typeof x === "string");
    const focused = typeof p.focused === "string" ? p.focused : null;
    return { open, focused };
  } catch {
    return null;
  }
}
