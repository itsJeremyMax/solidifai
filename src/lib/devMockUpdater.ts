/**
 * Dev-only update mock. Lets you exercise the whole updater UI — available →
 * downloading → ready → error — inside `tauri dev`, where the real updater is
 * deliberately disabled (a dev build has no signed installer to apply, so a real
 * check can only ever error).
 *
 * Enable it by opening the app with a `?mockUpdate` query param, e.g.
 *   http://localhost:1420/?mockUpdate#/           → follow your update-behavior setting
 *   http://localhost:1420/?mockUpdate=available#/ → just show the "available" indicator
 *   http://localhost:1420/?mockUpdate=download#/  → auto-download to "Restart to update"
 *   http://localhost:1420/?mockUpdate=silent#/    → silent background install
 *   http://localhost:1420/?mockUpdate=ready#/     → jump straight to "Restart to update"
 *   http://localhost:1420/?mockUpdate=error#/     → a download that fails
 *   …&mockVersion=1.4.0                            → override the offered version
 * (or set `localStorage.solidifaiMockUpdate` to any of those scenario strings).
 *
 * `readMockUpdateConfig` returns null in production (its first line is
 * `if (!import.meta.env.DEV) return null;`, statically true → the `?mockUpdate` /
 * localStorage reads are dead-code-eliminated), so the mock can never activate in a
 * production build. It never touches the real IPC or Rust side.
 */

/** Explicit scenarios, plus "behavior" which follows the user's updateBehavior. */
export type MockScenario = "behavior" | "available" | "download" | "silent" | "ready" | "error";

export interface MockUpdateConfig {
  scenario: MockScenario;
  /** An explicit ?mockVersion, or null to derive it from the running version. */
  version: string | null;
}

/**
 * The next version above `current` — a patch bump (0.3.0 → 0.3.1) — so a mock
 * update is always ahead of the installed build, no matter how far the real
 * version climbs. Falls back to a sensible default when the current version
 * isn't known yet or doesn't parse as x.y.z.
 */
export function nextMockVersion(current: string): string {
  const m = current.trim().match(/^(\d+)\.(\d+)\.(\d+)/);
  if (!m) return "1.4.0";
  return `${m[1]}.${m[2]}.${Number(m[3]) + 1}`;
}

const SCENARIOS: MockScenario[] = ["available", "download", "silent", "ready", "error"];

/** Read `?mockUpdate` (search or hash query) or the localStorage fallback. */
function readRaw(): { flag: string | null; version: string | null } {
  try {
    const search = new URLSearchParams(window.location.search);
    // Hash-router URLs can carry the query after the "#", e.g. "#/?mockUpdate=1".
    const hashQuery = window.location.hash.includes("?")
      ? new URLSearchParams(window.location.hash.slice(window.location.hash.indexOf("?") + 1))
      : null;
    const has = (k: string) => search.has(k) || (hashQuery?.has(k) ?? false);
    const get = (k: string) => search.get(k) ?? hashQuery?.get(k) ?? null;

    const version = get("mockVersion");
    if (has("mockUpdate")) return { flag: get("mockUpdate") ?? "", version };
    return { flag: window.localStorage.getItem("solidifaiMockUpdate"), version };
  } catch {
    return { flag: null, version: null };
  }
}

/** Believable release-notes body (markdown) for a mock update. No heading: every
 *  surface that shows these notes prints its own "What's new" title. */
export function mockUpdateNotes(): string {
  return [
    "- Live part validation now streams into the assemblies tree",
    "- Faster STEP import on large solids",
    "- Fixes the macOS 'damaged' launch warning on first open",
    "- Quieter offline update checks",
  ].join("\n");
}

/** The active mock config, or null when not in dev / not enabled. */
export function readMockUpdateConfig(): MockUpdateConfig | null {
  if (!import.meta.env.DEV) return null;
  const { flag, version } = readRaw();
  if (flag === null) return null;
  const s = flag.trim().toLowerCase();
  const scenario = (SCENARIOS.includes(s as MockScenario) ? s : "behavior") as MockScenario;
  // No explicit ?mockVersion → null, so the caller derives it from the running version.
  return { scenario, version: version?.trim() || null };
}

/**
 * Simulate a download: stream progress 0→1 over ~2.6s through `onProgress`,
 * then resolve. When `fail` is set it rejects partway to exercise the error UI.
 * `alive` lets the caller bail if the provider unmounted mid-download.
 */
export function simulateMockDownload(
  onProgress: (fraction: number) => void,
  alive: () => boolean,
  fail: boolean,
): Promise<void> {
  const total = 24.8 * 1024 * 1024; // a believable payload size
  return new Promise((resolve, reject) => {
    let downloaded = 0;
    const tick = () => {
      if (!alive()) return resolve();
      downloaded = Math.min(total, downloaded + total * (0.05 + Math.random() * 0.09));
      const fraction = downloaded / total;
      onProgress(Math.min(1, fraction));
      if (fail && fraction >= 0.55) {
        reject(new Error("Mock update download failed (network reset)."));
        return;
      }
      if (fraction >= 1) {
        resolve();
        return;
      }
      window.setTimeout(tick, 200);
    };
    window.setTimeout(tick, 250);
  });
}
