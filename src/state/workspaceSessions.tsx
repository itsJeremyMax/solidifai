import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { readOpenTabs, saveOpenTabs } from "../lib/openTabs";
import { listWorkspaces } from "../lib/workspaces";
import { clearEditorView } from "./editorViewState";
import { clearArtifactCache } from "../hooks/useArtifacts";

interface SessionsApi {
  /** Open workspace paths, in the order they were opened (tab order). */
  openPaths: string[];
  /** Open paths ordered most-recently-focused first (MRU). Same set as
   *  {@link openPaths}; the off-editor switcher menu uses it so the workspace you
   *  last viewed sits on top. The tab bar keeps {@link openPaths} order instead. */
  recentPaths: string[];
  /** The focused workspace path, or null when none is open. */
  focusedPath: string | null;
  /** Ensure a tab exists for this path (idempotent); does not change focus. */
  open: (path: string) => void;
  /** Open the path if absent, then focus it. */
  focus: (path: string) => void;
  /** Remove the tab; if it was focused, focus the last remaining tab (or null). */
  close: (path: string) => void;
  /** True if this path was part of the restored tab set (i.e. it was open last session). */
  wasRestored: (path: string) => boolean;
}

const Ctx = createContext<SessionsApi | null>(null);

export function WorkspaceSessionsProvider({ children }: { children: ReactNode }) {
  const saved = readOpenTabs();

  // Hydrate from persisted state; if nothing saved, start empty.
  const [openPaths, setOpenPaths] = useState<string[]>(saved?.open ?? []);
  const [focusedPath, setFocusedPath] = useState<string | null>(saved?.focused ?? null);

  // Focus recency, most-recent-first. Seeds the restored focused tab on top, then
  // the rest in open order as a best guess; updated on every focus(). Kept apart
  // from openPaths so the tab bar never reorders under the user.
  const [focusOrder, setFocusOrder] = useState<string[]>(() =>
    saved?.focused
      ? [saved.focused, ...(saved.open ?? []).filter((p) => p !== saved.focused)]
      : (saved?.open ?? []),
  );

  // Stable set of paths that were open at launch — used to show the "restored" note.
  const restoredPaths = useRef(new Set(saved?.open ?? []));

  // Persist whenever open set or focus changes.
  useEffect(() => {
    saveOpenTabs({ open: openPaths, focused: focusedPath });
  }, [openPaths, focusedPath]);

  // On mount, prune any restored tabs whose workspace no longer exists on disk.
  useEffect(() => {
    void listWorkspaces().then((workspaces) => {
      const knownPaths = new Set(workspaces.map((w) => w.path));
      setOpenPaths((prev) => {
        const next = prev.filter((p) => {
          const keep = knownPaths.has(p);
          if (!keep) restoredPaths.current.delete(p);
          return keep;
        });
        // If the set didn't change, return the same reference to avoid a re-render.
        if (next.length === prev.length) return prev;
        setFocusedPath((f) =>
          f !== null && !knownPaths.has(f) ? (next[next.length - 1] ?? null) : f,
        );
        return next;
      });
    });
    // Run once on mount only.
  }, []);

  const open = useCallback((path: string) => {
    setOpenPaths((p) => (p.includes(path) ? p : [...p, path]));
  }, []);

  const focus = useCallback((path: string) => {
    setOpenPaths((p) => (p.includes(path) ? p : [...p, path]));
    setFocusedPath(path);
    // Float to the front of the recency order (most recent first).
    setFocusOrder((order) => [path, ...order.filter((p) => p !== path)]);
  }, []);

  const close = useCallback((path: string) => {
    // Free cached state + GLB bytes for the closed workspace so they don't
    // accumulate in memory across the session.
    clearEditorView(path);
    clearArtifactCache(path);
    setFocusOrder((order) => order.filter((p) => p !== path));
    setOpenPaths((prev) => {
      const next = prev.filter((p) => p !== path);
      // Update focus in the same batch: if we closed the focused tab, move
      // focus to the last remaining tab (or null). Non-focused closes are a
      // no-op for focus. Calling a setter inside an updater is supported by
      // React and keeps both state slices consistent without an extra render.
      setFocusedPath((f) => (f === path ? (next[next.length - 1] ?? null) : f));
      return next;
    });
  }, []);

  const wasRestored = useCallback((path: string) => restoredPaths.current.has(path), []);

  const recentPaths = useMemo(() => {
    const rank = new Map(focusOrder.map((p, i) => [p, i] as const));
    // Stable sort by focus recency; tabs never focused fall to the end in their
    // existing open order (Infinity rank, original-index tiebreak).
    return openPaths
      .map((p, i) => [p, i] as const)
      .sort(([a, ai], [b, bi]) => (rank.get(a) ?? Infinity) - (rank.get(b) ?? Infinity) || ai - bi)
      .map(([p]) => p);
  }, [openPaths, focusOrder]);

  const api = useMemo<SessionsApi>(
    () => ({ openPaths, recentPaths, focusedPath, open, focus, close, wasRestored }),
    [openPaths, recentPaths, focusedPath, open, focus, close, wasRestored],
  );
  return <Ctx.Provider value={api}>{children}</Ctx.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useWorkspaceSessions() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useWorkspaceSessions used outside WorkspaceSessionsProvider");
  return v;
}
