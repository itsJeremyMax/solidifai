import { matchPath, useLocation } from "react-router-dom";
import AppShell from "./AppShell";
import { useWorkspaceSessions } from "../state/workspaceSessions";

/** One mounted editor session per open workspace; only the focused one, while on
 *  the editor index route, is visible + active. Background sessions stay mounted
 *  (terminals/agents alive) but hidden with their viewport unmounted. */
export default function WorkspaceSessions() {
  const { openPaths, focusedPath } = useWorkspaceSessions();
  const { pathname } = useLocation();
  const onEditorIndex = !!matchPath("/w/:wsPath", pathname); // index only, NOT /settings etc.
  return (
    <>
      {openPaths.map((path) => {
        const active = onEditorIndex && path === focusedPath;
        // Active session fills the routed area as a COLUMN — the WorkspaceToolbar
        // strip stacks above the 3-pane row (terminal · viewport · inspector).
        // Inactive sessions stay MOUNTED (terminals/agents alive) but display:none.
        // Use the `hidden` utility CLASS, not the HTML attribute: the attribute's
        // UA `display:none` loses to the `flex` utility in the cascade.
        return (
          <div key={path} className={active ? "flex min-h-0 w-full flex-1 flex-col" : "hidden"}>
            <AppShell wsPath={path} active={active} />
          </div>
        );
      })}
    </>
  );
}
