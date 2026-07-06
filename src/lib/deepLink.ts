import { editorPath } from "./routes";

/**
 * Map an incoming `solidifai://` deep link to an in-app route. The action is the
 * URL host (e.g. `solidifai://settings`); `workspace` carries the target folder
 * in `?path=`. Anything unknown or unparseable falls back to home.
 */
export function deepLinkToRoute(url: string): string {
  try {
    const u = new URL(url);
    const action = u.hostname || u.pathname.replace(/^\/+/, "").split("/")[0];
    switch (action) {
      case "settings":
        return "/settings";
      case "materials":
        return "/materials";
      case "factory":
        return "/factory";
      case "workspace": {
        const path = u.searchParams.get("path");
        return path ? editorPath(path) : "/";
      }
      default:
        return "/";
    }
  } catch {
    return "/";
  }
}
