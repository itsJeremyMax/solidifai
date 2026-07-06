import type { Workspace } from "../../lib/workspaces";
import type { ViewMode, ThumbMeta } from "../../lib/home";
import { WorkspaceGridCard } from "./WorkspaceGridCard";
import { WorkspaceListRow } from "./WorkspaceListRow";

interface GalleryProps {
  workspaces: Workspace[];
  view: ViewMode;
  thumbs: Record<string, { src: string | null; meta?: ThumbMeta }>;
  busyKey: string | null;
  onOpen: (ws: Workspace) => void;
  onEditDetails: (ws: Workspace) => void;
  onArchive: (ws: Workspace) => void;
  onRestore: (ws: Workspace) => void;
  onDelete: (ws: Workspace) => void;
  onAcceptName: (ws: Workspace) => void;
  onDismissName: (ws: Workspace) => void;
  onTagClick?: (tag: string) => void;
}

/**
 * Pure presentational gallery. Renders the pre-filtered, pre-sorted workspace
 * list in either grid or list layout. Empty-state decisions live in the parent.
 */
export function WorkspaceGallery({
  workspaces,
  view,
  thumbs,
  busyKey,
  onOpen,
  onEditDetails,
  onArchive,
  onRestore,
  onDelete,
  onAcceptName,
  onDismissName,
  onTagClick,
}: GalleryProps) {
  if (view === "grid") {
    return (
      <div
        style={{ gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))" }}
        className="grid gap-3"
      >
        {workspaces.map((ws) => (
          <WorkspaceGridCard
            key={ws.path}
            ws={ws}
            thumbSrc={thumbs[ws.path]?.src ?? null}
            thumb={thumbs[ws.path]?.meta}
            busy={busyKey === ws.path}
            disabled={busyKey != null && busyKey !== ws.path}
            onOpen={() => onOpen(ws)}
            onEditDetails={() => onEditDetails(ws)}
            onArchive={() => onArchive(ws)}
            onRestore={() => onRestore(ws)}
            onDelete={() => onDelete(ws)}
            onAcceptName={() => onAcceptName(ws)}
            onDismissName={() => onDismissName(ws)}
            onTagClick={onTagClick}
          />
        ))}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      {workspaces.map((ws) => (
        <WorkspaceListRow
          key={ws.path}
          ws={ws}
          thumbSrc={thumbs[ws.path]?.src ?? null}
          thumb={thumbs[ws.path]?.meta}
          busy={busyKey === ws.path}
          disabled={busyKey != null && busyKey !== ws.path}
          onOpen={() => onOpen(ws)}
          onEditDetails={() => onEditDetails(ws)}
          onArchive={() => onArchive(ws)}
          onRestore={() => onRestore(ws)}
          onDelete={() => onDelete(ws)}
          onAcceptName={() => onAcceptName(ws)}
          onDismissName={() => onDismissName(ws)}
          onTagClick={onTagClick}
        />
      ))}
    </div>
  );
}
