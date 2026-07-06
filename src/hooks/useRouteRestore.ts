import { useEffect, useRef } from "react";
import { matchPath, useLocation, useNavigate } from "react-router-dom";

import { readLastRoute, saveLastRoute } from "../lib/lastRoute";
import { decodeWsPath } from "../lib/routes";
import { listWorkspaces } from "../lib/workspaces";

/**
 * Persist the current route and, once on launch, restore the last one. If the app
 * launches on "/" and a route was saved, navigate there (replace). A saved editor
 * route whose workspace no longer exists is dropped (the app stays home). When the
 * app launches on a non-home route (e.g. a deep link), restore is skipped so it
 * doesn't override the requested destination.
 *
 * Mounted once in {@link AppLayout}.
 */
export function useRouteRestore() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const restored = useRef(false);

  // Persist the current route (the bare home route is the default, so skip it).
  useEffect(() => {
    if (pathname !== "/") saveLastRoute(pathname);
  }, [pathname]);

  // Restore once, only when we launched on home.
  useEffect(() => {
    if (restored.current) return;
    restored.current = true;
    if (pathname !== "/") return;

    const saved = readLastRoute();
    if (!saved || saved === "/") return;

    const m = matchPath("/w/:wsPath/*", saved) ?? matchPath("/w/:wsPath", saved);
    if (m?.params.wsPath) {
      const wsPath = decodeWsPath(m.params.wsPath);
      void listWorkspaces()
        .then((list) => {
          if (list.some((w) => w.path === wsPath)) navigate(saved, { replace: true });
        })
        .catch(() => {});
    } else {
      navigate(saved, { replace: true });
    }
    // Run exactly once on mount; `pathname`/`navigate` are read at launch on purpose.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
}
