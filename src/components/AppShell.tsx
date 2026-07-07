import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import TopBar from "./TopBar";
import WorkspaceToolbar from "./WorkspaceToolbar";
import { NameSuggestionBar } from "./NameSuggestionBar";
import InteractionPanel, { type InteractionTab } from "./InteractionPanel";
import EditorPanes from "./EditorPanes";
import { editorPath } from "../lib/routes";
import { basename, listWorkspaces } from "../lib/workspaces";

interface AppShellProps {
  /** Absolute workspace root path — this session's identity (PTY id + cwd). */
  wsPath: string;
  /**
   * Whether this session is the visible, focused one (on the editor index route).
   * Gates the heavy/focused-scoped parts (TopBar publish, viewport, inspector,
   * artifacts); the terminal stays mounted for every session regardless.
   */
  active: boolean;
}

/**
 * AppShell — one mounted editor session for a workspace. Always mounts the left
 * interaction pane (its terminal/agent must stay alive while in the background),
 * and — only when `active` — publishes the {@link TopBar} chrome and mounts the
 * focused-scoped {@link EditorPanes} (artifacts + viewport + inspector).
 *
 * The window chrome (AppHeader) lives in AppLayout; the editor publishes its
 * toolbar there via TopBar (a publisher that renders null) and fills the routed
 * area with its panes. Only the ACTIVE session may render TopBar — if every
 * mounted session published, they'd fight over the single header slot and a
 * background unmount could clear it.
 */
export default function AppShell({ wsPath, active }: AppShellProps) {
  const navigate = useNavigate();

  // Show the folder name immediately, then resolve the registered name (which can
  // differ after a rename) from the workspace registry.
  const [name, setName] = useState(() => basename(wsPath) || "Workspace");
  useEffect(() => {
    let live = true;
    listWorkspaces()
      .then((list) => {
        const ws = list.find((w) => w.path === wsPath);
        if (live && ws) setName(ws.name);
      })
      .catch(() => {});
    return () => {
      live = false;
    };
  }, [wsPath]);

  const onOpenSettings = () => navigate(`${editorPath(wsPath)}/settings`);
  const onOpenMaterials = () => navigate(`${editorPath(wsPath)}/materials`);
  const onOpenFactory = () => navigate(`${editorPath(wsPath)}/factory`);
  const onOpenReferences = () => navigate(`${editorPath(wsPath)}/references`);

  const [activeTab] = useState<InteractionTab>("terminal");

  return (
    <>
      {active && (
        <TopBar
          onOpenSettings={onOpenSettings}
          onOpenMaterials={onOpenMaterials}
          onOpenFactory={onOpenFactory}
          onOpenReferences={onOpenReferences}
        />
      )}
      {active && <WorkspaceToolbar workspaceName={name} />}
      {active && <NameSuggestionBar wsPath={wsPath} currentName={name} />}
      <div className="flex min-h-0 w-full flex-1">
        <InteractionPanel activeTab={activeTab} wsPath={wsPath} active={active} />
        {active && <EditorPanes activeTab={activeTab} wsPath={wsPath} />}
      </div>
    </>
  );
}
