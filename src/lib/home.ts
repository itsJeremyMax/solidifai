/**
 * Pure selection logic for the workspace library home. No IPC, no React — given
 * the raw registry + thumbnail metadata, derive the visible list, counts, and the
 * continue-hero. Kept pure so it is exhaustively unit-tested.
 */
import type { Workspace } from "./workspaces";

export type ViewMode = "grid" | "list";
export type HomeFilter = "all" | "recent" | "archived";

/** Per-workspace thumbnail metadata from the cache sidecar, keyed by path upstream. */
export interface ThumbMeta {
  /** Epoch ms the snapshot was captured. */
  capturedAt: number;
  /** Part count recorded at capture time. */
  partCount: number;
}

/** A workspace is "recent" if it was active within this window. */
export const RECENT_WINDOW_MS = 14 * 24 * 60 * 60 * 1000;

export function isArchived(ws: Workspace): boolean {
  return ws.archivedAt != null;
}

/** Most recent meaningful activity: last opened, last snapshot, else created. */
export function lastActiveAt(ws: Workspace, thumb?: ThumbMeta): number {
  const explicit = Math.max(ws.lastOpenedAt ?? 0, thumb?.capturedAt ?? 0);
  return explicit > 0 ? explicit : ws.createdAt;
}

export function isRecent(ws: Workspace, now: number, thumb?: ThumbMeta): boolean {
  return now - lastActiveAt(ws, thumb) <= RECENT_WINDOW_MS;
}

export interface SelectInput {
  workspaces: Workspace[];
  thumbs: Record<string, ThumbMeta>;
  filter: HomeFilter;
  query: string;
  now: number;
  tagFilter?: string | null;
}

export interface SelectResult {
  visible: Workspace[];
  counts: { all: number; archived: number };
}

/** Apply the active filter + search and sort, returning the visible set + counts. */
export function selectWorkspaces(input: SelectInput): SelectResult {
  const { workspaces, thumbs, filter, query, now } = input;
  const active = workspaces.filter((w) => !isArchived(w));
  const archived = workspaces.filter(isArchived);
  const counts = { all: active.length, archived: archived.length };

  let set: Workspace[];
  if (filter === "archived") {
    set = [...archived].sort((a, b) => (b.archivedAt ?? 0) - (a.archivedAt ?? 0));
  } else {
    set = [...active].sort(
      (a, b) => lastActiveAt(b, thumbs[b.path]) - lastActiveAt(a, thumbs[a.path]),
    );
    if (filter === "recent") set = set.filter((w) => isRecent(w, now, thumbs[w.path]));
  }

  const q = query.trim().toLowerCase();
  let visible = q ? set.filter((w) => matchesQuery(w, q)) : set;
  const tag = input.tagFilter?.trim().toLowerCase();
  if (tag) visible = visible.filter((w) => w.tags.some((t) => t.toLowerCase() === tag));
  return { visible, counts };
}

function matchesQuery(w: Workspace, q: string): boolean {
  if (w.name.toLowerCase().includes(q)) return true;
  if ((w.description ?? "").toLowerCase().includes(q)) return true;
  return w.tags.some((t) => t.toLowerCase().includes(q));
}

/** The continue-hero workspace, or null. Only the default view (All, no query) shows it. */
export function heroWorkspace(input: SelectInput): Workspace | null {
  if (input.filter !== "all" || input.query.trim() !== "") return null;
  const active = input.workspaces.filter((w) => !isArchived(w));
  if (active.length === 0) return null;
  return [...active].sort(
    (a, b) => lastActiveAt(b, input.thumbs[b.path]) - lastActiveAt(a, input.thumbs[a.path]),
  )[0];
}
