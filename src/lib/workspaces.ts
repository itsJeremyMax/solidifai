/**
 * Typed wrappers over the Rust workspace + template commands
 * (registry / lifecycle / overridable template store).
 *
 * Every `invoke` is wrapped in try/catch with a graceful fallback so the
 * launcher and settings pages never throw into the render path:
 *   • read-style queries (`list_workspaces`, `get_active_workspace`,
 *     `get_templates`, `pick_directory`) resolve to a safe empty/`null` value
 *     on failure — the UI shows an empty/idle state.
 *   • mutating actions that the user explicitly triggers
 *     (`create_workspace`, `open_workspace`, `save_template`, `reset_template`)
 *     re-throw so the caller can surface the backend error message inline.
 *
 * Also exports small presentation helpers: a `~`-collapsing path formatter and
 * a compact relative-time formatter ("just now", "3h ago", "Apr 12").
 */
import { invoke } from "@tauri-apps/api/core";

/* ───────────────────────────────── types ──────────────────────────────── */

/** A registered workspace (a provisioned solidifai project directory). */
export interface Workspace {
  name: string;
  path: string;
  /** Epoch millis the workspace was created. */
  createdAt: number;
  /** Epoch millis it was last opened, or `null` if never opened since create. */
  lastOpenedAt: number | null;
  /** Epoch millis the workspace was archived, or `null` if active. */
  archivedAt: number | null;
  /** Short description cached from workspace.json, or `null` if not set. */
  description: string | null;
  /** User-applied tags cached from workspace.json. */
  tags: string[];
  /** Name proposed by the agent (pending user acceptance), or `null`. */
  proposedName: string | null;
}

/** The overridable default file written into every new workspace. */
export type TemplateName = "AGENTS.md";

/** An overridable workspace template. `isCustom` ⇒ user has edited the default. */
export interface Template {
  name: TemplateName;
  content: string;
  /** True when the stored content differs from the shipped default. */
  isCustom: boolean;
}

/* ─────────────────────── runtime validation helpers ───────────────────── */

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

/** Validate + normalize one raw workspace record; returns `null` if malformed. */
function toWorkspace(v: unknown): Workspace | null {
  if (!isRecord(v)) return null;
  if (typeof v.name !== "string" || typeof v.path !== "string") return null;
  if (typeof v.createdAt !== "number") return null;
  const lastOpenedAt = typeof v.lastOpenedAt === "number" ? v.lastOpenedAt : null;
  const archivedAt = typeof v.archivedAt === "number" ? v.archivedAt : null;
  const description = typeof v.description === "string" ? v.description : null;
  const tags = Array.isArray(v.tags) ? v.tags.filter((t) => typeof t === "string") : [];
  const proposedName = typeof v.proposedName === "string" ? v.proposedName : null;
  return {
    name: v.name,
    path: v.path,
    createdAt: v.createdAt,
    lastOpenedAt,
    archivedAt,
    description,
    tags,
    proposedName,
  };
}

const TEMPLATE_NAMES: readonly TemplateName[] = ["AGENTS.md"];

/** Validate + normalize one raw template record; returns `null` if malformed. */
function toTemplate(v: unknown): Template | null {
  if (!isRecord(v)) return null;
  if (typeof v.name !== "string" || !TEMPLATE_NAMES.includes(v.name as TemplateName)) {
    return null;
  }
  if (typeof v.content !== "string") return null;
  return {
    name: v.name as TemplateName,
    content: v.content,
    isCustom: v.isCustom === true,
  };
}

/* ──────────────────────────── workspace registry ──────────────────────── */

/**
 * List every registered workspace. Resolves to `[]` on any failure (command
 * unavailable, backend not ready) so the launcher renders its empty state.
 */
export async function listWorkspaces(): Promise<Workspace[]> {
  try {
    const raw = await invoke<unknown>("list_workspaces");
    if (!Array.isArray(raw)) return [];
    return raw.map(toWorkspace).filter((w): w is Workspace => w !== null);
  } catch {
    return [];
  }
}

/**
 * Create a new workspace under `parentDir` and open it. The backend provisions
 * the directory (engine env warms asynchronously after open).
 *
 * @throws Re-throws the backend error (e.g. name taken / not writable) so the
 *   launcher can surface it inline next to the create form.
 */
export async function createWorkspace(name: string, parentDir: string): Promise<Workspace> {
  const raw = await invoke<unknown>("create_workspace", { name, parentDir });
  const ws = toWorkspace(raw);
  if (!ws) throw new Error("create_workspace returned an unexpected result");
  return ws;
}

/**
 * Open an existing workspace by absolute path (makes it the active workspace).
 *
 * @throws Re-throws the backend error so the caller can surface it inline.
 */
export async function openWorkspace(path: string): Promise<Workspace> {
  const raw = await invoke<unknown>("open_workspace", { path });
  const ws = toWorkspace(raw);
  if (!ws) throw new Error("open_workspace returned an unexpected result");
  return ws;
}

/**
 * Rename a workspace (by absolute path) to `newName`. Returns the updated
 * registry record.
 *
 * @throws Re-throws the backend error (e.g. name taken / not writable) so the
 *   launcher can surface it inline in the rename dialog.
 */
export async function renameWorkspace(path: string, newName: string): Promise<Workspace> {
  const raw = await invoke<unknown>("rename_workspace", { path, newName });
  const ws = toWorkspace(raw);
  if (!ws) throw new Error("rename_workspace returned an unexpected result");
  return ws;
}

/**
 * Edit a workspace's description and tags (cached from workspace.json). Returns
 * the updated registry record.
 *
 * @throws Re-throws the backend error so the caller can surface it inline.
 */
export async function editWorkspaceDetails(
  path: string,
  description: string | null,
  tags: string[],
): Promise<Workspace> {
  const raw = await invoke<unknown>("edit_workspace_details", { path, description, tags });
  const ws = toWorkspace(raw);
  if (!ws) throw new Error("edit_workspace_details returned an unexpected result");
  return ws;
}

/**
 * Accept a name proposed by the agent, applying it as the workspace's name.
 * Returns the updated registry record.
 *
 * @throws Re-throws the backend error so the caller can surface it inline.
 */
export async function acceptProposedName(path: string, name: string): Promise<Workspace> {
  const raw = await invoke<unknown>("accept_proposed_name", { path, name });
  const ws = toWorkspace(raw);
  if (!ws) throw new Error("accept_proposed_name returned an unexpected result");
  return ws;
}

/**
 * Dismiss a pending proposed name without applying it. Returns the updated
 * registry record (with `proposedName` cleared).
 *
 * @throws Re-throws the backend error so the caller can surface it inline.
 */
export async function dismissProposedName(path: string): Promise<Workspace> {
  const raw = await invoke<unknown>("dismiss_proposed_name", { path });
  const ws = toWorkspace(raw);
  if (!ws) throw new Error("dismiss_proposed_name returned an unexpected result");
  return ws;
}

/**
 * Delete a workspace from the registry. When `deleteFiles` is true the backend
 * also removes the workspace folder from disk (destructive); otherwise only the
 * registry entry is dropped and the files are left in place.
 *
 * @throws Re-throws the backend error so the launcher can surface it inline.
 */
export async function deleteWorkspace(path: string, deleteFiles: boolean): Promise<void> {
  await invoke("delete_workspace", { path, deleteFiles });
}

/**
 * Archive a workspace (hidden from the main view; files stay on disk). Reversible.
 * @throws Re-throws the backend error so the caller can surface it inline.
 */
export async function archiveWorkspace(path: string): Promise<Workspace> {
  const raw = await invoke<unknown>("archive_workspace", { path });
  const ws = toWorkspace(raw);
  if (!ws) throw new Error("archive_workspace returned an unexpected result");
  return ws;
}

/** Restore an archived workspace back into the active set. @throws on backend error. */
export async function restoreWorkspace(path: string): Promise<Workspace> {
  const raw = await invoke<unknown>("restore_workspace", { path });
  const ws = toWorkspace(raw);
  if (!ws) throw new Error("restore_workspace returned an unexpected result");
  return ws;
}

/**
 * Return to the launcher: clear focus + drop the viewport watcher. With N live
 * instances this does NOT tear any engine down — every open workspace keeps
 * running in the background. Never throws.
 */
export async function closeWorkspace(): Promise<void> {
  try {
    await invoke("close_workspace");
  } catch {
    // Best-effort: a failed close shouldn't block returning to the launcher.
  }
}

/**
 * Tear down exactly ONE workspace tab by absolute path: kill its engine + reap its
 * agent shell + drop it from the live registry. If it was the focused tab, focus is
 * cleared backend-side (the caller then focuses a sibling).
 *
 * @throws Re-throws the backend error so the caller can surface it inline.
 */
export async function closeWorkspaceTab(path: string): Promise<void> {
  await invoke("close_workspace_tab", { path });
}

/** The live tab set + which one is focused (for the switcher + restore). */
export interface OpenWorkspaces {
  /** Canonical root paths of every currently-live workspace. */
  open: string[];
  /** The focused workspace's path, or `null` when the launcher is showing. */
  focused: string | null;
}

/**
 * List the live workspace tabs + the focused one. Resolves to an empty set on any
 * failure so the switcher renders an idle state instead of throwing.
 */
export async function listOpenWorkspaces(): Promise<OpenWorkspaces> {
  try {
    const raw = await invoke<unknown>("list_open_workspaces");
    if (!isRecord(raw)) return { open: [], focused: null };
    const open = Array.isArray(raw.open)
      ? raw.open.filter((p): p is string => typeof p === "string")
      : [];
    const focused = typeof raw.focused === "string" ? raw.focused : null;
    return { open, focused };
  } catch {
    return { open: [], focused: null };
  }
}

/** The currently active workspace, or `null` if none is open / on failure. */
export async function getActiveWorkspace(): Promise<Workspace | null> {
  try {
    const raw = await invoke<unknown>("get_active_workspace");
    return toWorkspace(raw);
  } catch {
    return null;
  }
}

/**
 * Open the native folder picker. Resolves to the chosen absolute path, or
 * `null` if the user cancels / the command is unavailable.
 */
export async function pickDirectory(): Promise<string | null> {
  try {
    const raw = await invoke<unknown>("pick_directory");
    return typeof raw === "string" ? raw : null;
  } catch {
    return null;
  }
}

/**
 * The default *parent* directory for a new workspace (the last-used location,
 * else `<Documents>/Solidifai/workspaces`). Resolves to `null` on failure so the
 * launcher falls back to today's require-an-explicit-pick behavior.
 */
export async function defaultWorkspaceDir(): Promise<string | null> {
  try {
    const raw = await invoke<unknown>("default_workspace_dir");
    return typeof raw === "string" && raw.length > 0 ? raw : null;
  } catch {
    return null;
  }
}

/* ──────────────────────────── template store ──────────────────────────── */

/**
 * Read the overridable workspace templates. Resolves to `[]` on failure
 * so the settings page degrades to an empty (non-crashing) state.
 */
export async function getTemplates(): Promise<Template[]> {
  try {
    const raw = await invoke<unknown>("get_templates");
    if (!Array.isArray(raw)) return [];
    return raw.map(toTemplate).filter((t): t is Template => t !== null);
  } catch {
    return [];
  }
}

/**
 * Persist an edited template. The next created workspace uses the new content.
 *
 * @throws Re-throws the backend error so settings can surface it inline.
 */
export async function saveTemplate(name: TemplateName, content: string): Promise<void> {
  await invoke("save_template", { name, content });
}

/**
 * Reset a template back to its shipped default (clears the override).
 *
 * @throws Re-throws the backend error so settings can surface it inline.
 */
export async function resetTemplate(name: TemplateName): Promise<void> {
  await invoke("reset_template", { name });
}

/* ──────────────────────────── thumbnails ──────────────────────────────── */

/** A cached workspace thumbnail (PNG data URL) + its metadata. */
export interface WorkspaceThumbnail {
  path: string;
  dataUrl: string;
  capturedAt: number;
  partCount: number;
}

/** List cached workspace thumbnails (data URLs). Resolves to [] on any failure. */
export async function listWorkspaceThumbnails(): Promise<WorkspaceThumbnail[]> {
  try {
    const raw = await invoke<unknown>("list_workspace_thumbnails");
    if (!Array.isArray(raw)) return [];
    return raw.filter(
      (e): e is WorkspaceThumbnail =>
        typeof e === "object" &&
        e !== null &&
        typeof (e as WorkspaceThumbnail).path === "string" &&
        typeof (e as WorkspaceThumbnail).dataUrl === "string" &&
        typeof (e as WorkspaceThumbnail).capturedAt === "number" &&
        typeof (e as WorkspaceThumbnail).partCount === "number",
    );
  } catch {
    return [];
  }
}

/** Persist a captured PNG for a workspace (best-effort; never throws). */
export async function storeWorkspaceThumbnail(
  path: string,
  png: Uint8Array,
  partCount: number,
): Promise<void> {
  try {
    await invoke("store_workspace_thumbnail", { path, png: Array.from(png), partCount });
  } catch {
    // best-effort: a failed capture just leaves the placeholder.
  }
}

/* ──────────────────────────── presentation ────────────────────────────── */

/**
 * Last path segment for display fallbacks (workspace tab/title names).
 * Separator-blind: registry paths are native, so Windows hands us backslashes
 * where a bare split("/") would return the entire absolute path.
 */
export function basename(path: string): string {
  return path.split(/[\\/]/).pop() ?? "";
}

/**
 * Collapse a leading home directory to `~` for display: `/Users/<name>` or
 * `/home/<name>` on POSIX, `C:\Users\<name>` (any drive letter) on Windows.
 * Matches the `tildePath` convention used elsewhere in the inspector.
 */
export function tildePath(path: string): string {
  return path.replace(/^\/(Users|home)\/[^/]+/, "~").replace(/^[a-z]:\\Users\\[^\\]+/i, "~");
}

/**
 * Compact relative-time label for a "last opened" timestamp (epoch millis).
 * Returns "Never opened" for `null`, and degrades to an absolute date past a
 * week ("Apr 12" / "Apr 12, 2024").
 */
export function relativeTime(ms: number | null, now: number = Date.now()): string {
  if (ms === null) return "Never opened";
  const diff = now - ms;
  if (diff < 0) return "just now";

  const sec = Math.floor(diff / 1000);
  if (sec < 45) return "just now";

  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;

  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;

  const day = Math.floor(hr / 24);
  if (day < 7) return day === 1 ? "yesterday" : `${day}d ago`;

  const date = new Date(ms);
  const sameYear = date.getFullYear() === new Date(now).getFullYear();
  return date.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    ...(sameYear ? {} : { year: "numeric" }),
  });
}
