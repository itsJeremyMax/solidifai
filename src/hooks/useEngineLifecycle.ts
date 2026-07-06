import { useEffect, useRef } from "react";
import { matchPath, useLocation } from "react-router-dom";
import { openWorkspace } from "../lib/workspaces";
import { decodeWsPath } from "../lib/routes";

/** The active workspace path encoded in the current location, or null. */
function activeWsPath(pathname: string): string | null {
  const m = matchPath("/w/:wsPath/*", pathname) ?? matchPath("/w/:wsPath", pathname);
  return m?.params.wsPath ? decodeWsPath(m.params.wsPath) : null;
}

/**
 * Ensure + focus the engine workspace as the route enters the `/w/:wsPath`
 * subtree. With N live instances, navigation NEVER closes a tab — leaving a
 * workspace (to the launcher or to another workspace) leaves its engine running in
 * the background; `openWorkspace` is ensure+focus server-side, so re-entering an
 * already-open workspace just re-focuses it. Tearing a tab down is an explicit
 * action (`closeWorkspaceTab`), not a navigation side effect.
 *
 * Centralized here (watching location transitions) rather than in an EditorSession
 * unmount effect, so React StrictMode double-mounts can't spuriously fire, and
 * deep-link / restore entries focus correctly.
 *
 * Mounted once in {@link AppLayout}, which never unmounts across navigation — so
 * the `prev` ref persists and each transition is handled exactly once.
 */
export function useEngineLifecycle() {
  const { pathname } = useLocation();
  const prev = useRef<string | null>(null);

  useEffect(() => {
    const next = activeWsPath(pathname);
    if (prev.current === next) return;
    if (next) void openWorkspace(next); // ensure+focus; never closes another tab
    prev.current = next;
  }, [pathname]);
}
