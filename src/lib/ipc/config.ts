import { invoke } from "./core";

/* ───────────────────────────── app-config ─────────────────────────────── */

/** How the app applies an available update (mirrors the Rust contract). */
export type UpdateBehavior = "notify" | "autoDownload" | "silent";
/** Release channel the updater checks. */
export type UpdateChannel = "stable" | "beta";

/** Global app config (mirrors the Rust `AppConfig` camelCase contract): viewport
 *  feature flags plus update behavior, channel, and the last-seen app version. */
export interface AppConfig {
  gtao: boolean;
  grid: boolean;
  smaa: boolean;
  softShadows: boolean;
  updateBehavior: UpdateBehavior;
  updateChannel: UpdateChannel;
  /** Whether the app checks for updates automatically (launch, timer, focus). */
  backgroundUpdateChecks: boolean;
  /** App version whose what's-new the user has seen; null until first dismiss. */
  lastSeenVersion: string | null;
  /** Home library view mode. */
  homeView: "grid" | "list";
  /** Home library filter. */
  homeFilter: "all" | "recent" | "archived";
  /** Workspace path whose continue-hero was dismissed, or null. */
  homeHeroDismissed: string | null;
}

/** The shipped defaults; used when the backend is unavailable so the UI never crashes. */
export const DEFAULT_APP_CONFIG: AppConfig = {
  gtao: true,
  grid: true,
  smaa: true,
  softShadows: true,
  updateBehavior: "notify",
  updateChannel: "stable",
  backgroundUpdateChecks: true,
  lastSeenVersion: null,
  homeView: "grid",
  homeFilter: "all",
  homeHeroDismissed: null,
};

const UPDATE_BEHAVIORS: readonly UpdateBehavior[] = ["notify", "autoDownload", "silent"];
const UPDATE_CHANNELS: readonly UpdateChannel[] = ["stable", "beta"];

/** Validate + normalize a raw app-config record, filling any missing field from defaults. */
function toAppConfig(v: unknown): AppConfig {
  if (typeof v !== "object" || v === null) return DEFAULT_APP_CONFIG;
  const r = v as Record<string, unknown>;
  return {
    gtao: typeof r.gtao === "boolean" ? r.gtao : DEFAULT_APP_CONFIG.gtao,
    grid: typeof r.grid === "boolean" ? r.grid : DEFAULT_APP_CONFIG.grid,
    smaa: typeof r.smaa === "boolean" ? r.smaa : DEFAULT_APP_CONFIG.smaa,
    softShadows:
      typeof r.softShadows === "boolean" ? r.softShadows : DEFAULT_APP_CONFIG.softShadows,
    updateBehavior: UPDATE_BEHAVIORS.includes(r.updateBehavior as UpdateBehavior)
      ? (r.updateBehavior as UpdateBehavior)
      : DEFAULT_APP_CONFIG.updateBehavior,
    updateChannel: UPDATE_CHANNELS.includes(r.updateChannel as UpdateChannel)
      ? (r.updateChannel as UpdateChannel)
      : DEFAULT_APP_CONFIG.updateChannel,
    backgroundUpdateChecks:
      typeof r.backgroundUpdateChecks === "boolean"
        ? r.backgroundUpdateChecks
        : DEFAULT_APP_CONFIG.backgroundUpdateChecks,
    lastSeenVersion: typeof r.lastSeenVersion === "string" ? r.lastSeenVersion : null,
    homeView: r.homeView === "list" ? "list" : DEFAULT_APP_CONFIG.homeView,
    homeFilter:
      r.homeFilter === "recent" || r.homeFilter === "archived"
        ? r.homeFilter
        : DEFAULT_APP_CONFIG.homeFilter,
    homeHeroDismissed: typeof r.homeHeroDismissed === "string" ? r.homeHeroDismissed : null,
  };
}

/**
 * Read the global app-config. Resolves to {@link DEFAULT_APP_CONFIG} on any
 * failure (command unavailable, backend not ready) so the viewport always has a
 * valid config.
 */
export async function getAppConfig(): Promise<AppConfig> {
  try {
    return toAppConfig(await invoke<unknown>("get_app_config"));
  } catch {
    return DEFAULT_APP_CONFIG;
  }
}

/**
 * Apply a PARTIAL patch (only the changed flags) to the global app-config and
 * persist it. Returns the merged, authoritative config from the backend.
 *
 * @throws Re-throws the backend error so the store can revert the optimistic
 *   toggle and surface a non-blocking message.
 */
export async function setAppConfig(patch: Partial<AppConfig>): Promise<AppConfig> {
  return toAppConfig(await invoke<unknown>("set_app_config", { patch }));
}

/* ─────────────────────────────── updater ──────────────────────────────── */

/** Result of an update check: availability, version, and release notes when present. */
export interface UpdateCheck {
  available: boolean;
  version: string | null;
  /** Release notes (markdown) for the available version, or null when unknown. */
  notes: string | null;
}

/**
 * Check the given release channel for an available update (Rust `check_for_update`).
 * Re-throws on failure so the caller can surface the error state.
 */
export async function checkForUpdate(channel: UpdateChannel): Promise<UpdateCheck> {
  const r = await invoke<Partial<UpdateCheck>>("check_for_update", { channel });
  return { available: !!r.available, version: r.version ?? null, notes: r.notes ?? null };
}

/**
 * Download and install the available update for the channel (Rust
 * `download_and_install`). Resolves when the install finishes; download progress
 * arrives on the `updater://progress` event. Re-throws on failure.
 */
export async function downloadAndInstall(channel: UpdateChannel): Promise<void> {
  await invoke("download_and_install", { channel });
}

/**
 * Relaunch the app to apply an installed update (Rust `relaunch_for_update`).
 * Uses a single-instance-safe relaunch: it waits for this process to fully exit
 * (releasing the single-instance lock) before starting the new one, so the fresh
 * instance isn't killed by the guard. Re-throws on failure.
 */
export async function relaunchForUpdate(): Promise<void> {
  await invoke("relaunch_for_update");
}

/* ──────────────────────────── agent-config ────────────────────────────── */

/** The native coding harnesses the desktop provisioner can support. */
export type HarnessId = "codex" | "claudeCode" | "openCode" | "geminiCli" | "copilotCli" | "pi";

/**
 * Readiness states exposed by the harness support surface. The current backend
 * emits the first three values; the latter two keep the UI safe if an older or
 * newer backend cannot report a concrete result.
 */
export type HarnessState = "ready" | "notInstalled" | "needsSetup" | "unknown" | "unavailable";

/** One native coding harness and its current readiness for the active workspace. */
export interface HarnessStatus {
  id: HarnessId;
  displayName: string;
  state: HarnessState;
  remediation: string | null;
  userOwnedPaths: string[];
}

/** Files handled, preserved, or rejected by one provisioning pass. */
export interface ProvisionReport {
  written: string[];
  skippedUserOwned: string[];
  errors: string[];
}

/** Result of explicitly refreshing native agent support for the active workspace. */
export interface RefreshAgentSupportResult {
  provisionReport: ProvisionReport;
  statuses: HarnessStatus[];
}

const HARNESS_IDS: readonly HarnessId[] = [
  "codex",
  "claudeCode",
  "openCode",
  "geminiCli",
  "copilotCli",
  "pi",
];
const HARNESS_STATES: readonly HarnessState[] = [
  "ready",
  "notInstalled",
  "needsSetup",
  "unknown",
  "unavailable",
];

function toHarnessStatus(raw: unknown): HarnessStatus | null {
  if (typeof raw !== "object" || raw === null) return null;
  const record = raw as Record<string, unknown>;
  if (
    !HARNESS_IDS.includes(record.id as HarnessId) ||
    typeof record.displayName !== "string" ||
    !HARNESS_STATES.includes(record.state as HarnessState) ||
    (record.remediation !== null && typeof record.remediation !== "string") ||
    !Array.isArray(record.userOwnedPaths) ||
    !record.userOwnedPaths.every((path) => typeof path === "string")
  ) {
    return null;
  }
  return {
    id: record.id as HarnessId,
    displayName: record.displayName,
    state: record.state as HarnessState,
    remediation: record.remediation,
    userOwnedPaths: record.userOwnedPaths as string[],
  };
}

function toProvisionReport(raw: unknown): ProvisionReport {
  if (typeof raw !== "object" || raw === null)
    return { written: [], skippedUserOwned: [], errors: [] };
  const record = raw as Record<string, unknown>;
  const strings = (value: unknown) =>
    Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
  return {
    written: strings(record.written),
    skippedUserOwned: strings(record.skippedUserOwned),
    errors: strings(record.errors),
  };
}

function toRefreshAgentSupportResult(raw: unknown): RefreshAgentSupportResult {
  if (typeof raw !== "object" || raw === null) {
    return { provisionReport: toProvisionReport(null), statuses: [] };
  }
  const record = raw as Record<string, unknown>;
  return {
    provisionReport: toProvisionReport(record.provisionReport),
    statuses: Array.isArray(record.statuses)
      ? record.statuses
          .map(toHarnessStatus)
          .filter((status): status is HarnessStatus => status !== null)
      : [],
  };
}

/**
 * Get cached native harness readiness. This is a safe read so settings remains
 * usable against an unavailable or older backend.
 */
export async function getAgentHarnessStatuses(): Promise<HarnessStatus[]> {
  try {
    const raw = await invoke<unknown>("get_agent_harness_statuses");
    return Array.isArray(raw)
      ? raw.map(toHarnessStatus).filter((status): status is HarnessStatus => status !== null)
      : [];
  } catch {
    return [];
  }
}

/**
 * Re-provision the active workspace and explicitly re-check harness readiness.
 * Unlike the safe read, failures are re-thrown for the settings UI to display.
 */
export async function refreshAgentSupport(): Promise<RefreshAgentSupportResult> {
  return toRefreshAgentSupportResult(await invoke<unknown>("refresh_agent_support"));
}

/** One available workspace skill with its enabled state (mirrors Rust `SkillInfo`). */
export interface SkillInfo {
  name: string;
  description: string;
  enabled: boolean;
}

/** Per-workspace agent config (mirrors the Rust `AgentConfig` camelCase contract). */
export interface AgentConfig {
  /** Enabled skill names, or `null` ⇒ all skills enabled (the shipped default). */
  enabledSkills: string[] | null;
  /** Whether the provisioner manages (writes) the workspace skill tree. */
  autoProvisionSkills: boolean;
}

/**
 * List the active workspace's available skills + enabled state. Resolves to `[]`
 * on failure (no workspace open / command unavailable) so settings degrades to an
 * empty (non-crashing) state.
 */
export async function listSkills(): Promise<SkillInfo[]> {
  try {
    const raw = await invoke<unknown>("list_skills");
    if (!Array.isArray(raw)) return [];
    return raw.filter(
      (s): s is SkillInfo =>
        typeof s === "object" &&
        s !== null &&
        typeof (s as SkillInfo).name === "string" &&
        typeof (s as SkillInfo).description === "string" &&
        typeof (s as SkillInfo).enabled === "boolean",
    );
  } catch {
    return [];
  }
}

/** Read the active workspace's agent config, or `null` on failure / no workspace. */
export async function getAgentConfig(): Promise<AgentConfig | null> {
  try {
    const raw = await invoke<unknown>("get_agent_config");
    if (typeof raw !== "object" || raw === null) return null;
    const r = raw as Record<string, unknown>;
    const enabledSkills = Array.isArray(r.enabledSkills)
      ? (r.enabledSkills.filter((x) => typeof x === "string") as string[])
      : null;
    return {
      enabledSkills,
      autoProvisionSkills: r.autoProvisionSkills === true,
    };
  } catch {
    return null;
  }
}

/**
 * Persist the active workspace's agent config. The new skill set takes effect on
 * the next workspace open (the provisioner re-runs).
 *
 * @throws Re-throws the backend error so the settings UI can surface it inline.
 */
export async function setAgentConfig(config: AgentConfig): Promise<AgentConfig> {
  await invoke("set_agent_config", { config });
  return config;
}
