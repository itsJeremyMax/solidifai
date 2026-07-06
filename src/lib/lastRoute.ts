/**
 * Last-route persistence for restore-on-launch. Pure UI state, so it lives in
 * localStorage (like `useInspectorPrefs`) rather than the Rust-backed appConfig —
 * no backend round-trip, no schema change. Reads are guarded; writes best-effort.
 */
const KEY = "solidifai.lastRoute";

export function readLastRoute(): string | null {
  try {
    const v = localStorage.getItem(KEY);
    return v && v.length > 0 ? v : null;
  } catch {
    return null;
  }
}

export function saveLastRoute(path: string): void {
  try {
    localStorage.setItem(KEY, path);
  } catch {
    /* best-effort */
  }
}
