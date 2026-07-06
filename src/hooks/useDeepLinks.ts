import { useEffect } from "react";
import { matchPath, useNavigate } from "react-router-dom";

import { deepLinkToRoute } from "../lib/deepLink";
import { decodeWsPath } from "../lib/routes";
import { listWorkspaces } from "../lib/workspaces";

/**
 * Route incoming `solidifai://` deep links. Handles both the launch URL (app
 * started by a link) and links received while running. A workspace link whose
 * folder no longer exists falls back to home. The plugin is imported dynamically
 * and guarded, so this is a no-op outside a Tauri deep-link context (web preview,
 * tests). Mounted once in {@link AppLayout}.
 */
export function useDeepLinks() {
  const navigate = useNavigate();

  useEffect(() => {
    let active = true;
    let unlisten: (() => void) | undefined;

    // Resolve a deep link to a route, validating workspace targets against the
    // registry so a stale `solidifai://workspace?path=...` lands home, not on a
    // broken editor shell.
    const go = async (url: string, replace: boolean) => {
      const route = deepLinkToRoute(url);
      const m = matchPath("/w/:wsPath/*", route) ?? matchPath("/w/:wsPath", route);
      if (m?.params.wsPath) {
        const wsPath = decodeWsPath(m.params.wsPath);
        const list = await listWorkspaces().catch(() => []);
        if (!active) return;
        navigate(list.some((w) => w.path === wsPath) ? route : "/", { replace });
      } else {
        navigate(route, { replace });
      }
    };

    void (async () => {
      try {
        const { onOpenUrl, getCurrent } = await import("@tauri-apps/plugin-deep-link");
        const launch = await getCurrent();
        if (active && launch && launch.length > 0) await go(launch[0], true);
        const off = await onOpenUrl((urls) => {
          if (urls.length > 0) void go(urls[0], false);
        });
        if (active) unlisten = off;
        else off();
      } catch {
        /* no deep-link plugin available (web preview / tests) */
      }
    })();

    return () => {
      active = false;
      unlisten?.();
    };
  }, [navigate]);
}
