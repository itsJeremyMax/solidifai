/**
 * HomeView — the full-window home / workspace library (the `/` route). Replaces
 * the old single-column Launcher with a hero + searchable, filterable gallery.
 *
 * Data flow mirrors the old Launcher:
 *   • `listWorkspaces()` on mount → cards (fails → empty state, never throws).
 *   • Clicking a card / Continue → `openWorkspace(path)` → navigate to the editor.
 *   • New workspace → modal composer → `createWorkspace` → navigate to the editor.
 *   • Rename / delete / archive / restore mutate the registry and `refresh()`.
 *
 * View + filter are persisted app config (`homeView` / `homeFilter`); the search
 * query is local, ephemeral state. Pure selection (visible set, counts, hero)
 * lives in `lib/home.ts`; this component only wires state → those selectors →
 * the presentational pieces.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, BookMarked, Factory, SwatchBook } from "lucide-react";
import { revealItemInDir } from "@tauri-apps/plugin-opener";

import {
  acceptProposedName,
  archiveWorkspace,
  createWorkspace,
  deleteWorkspace,
  dismissProposedName,
  editWorkspaceDetails,
  listWorkspaces,
  listWorkspaceThumbnails,
  openWorkspace,
  restoreWorkspace,
  type Workspace,
} from "../../lib/workspaces";
import { heroWorkspace, selectWorkspaces, type ThumbMeta } from "../../lib/home";
import { useAppConfig } from "../../state/appConfig";
import { useHeaderSlot } from "../../state/headerSlot";
import { useWorkspaceSessions } from "../../state/workspaceSessions";
import UtilityCluster from "../UtilityCluster";
import { ContinueHero } from "./ContinueHero";
import { LibraryToolbar } from "./LibraryToolbar";
import { WorkspaceGallery } from "./WorkspaceGallery";
import { NewWorkspaceDialog } from "./NewWorkspaceDialog";
import { NoResults } from "./NoResults";
import { EmptyState } from "./EmptyState";
import { EditDetailsDialog } from "./EditDetailsDialog";
import { DeleteDialog } from "./DeleteDialog";
import { ArchiveToast } from "./ArchiveToast";

/** Shared lucide stroke weight to match the design language. */
const ICON_STROKE = 1.7;

interface HomeViewProps {
  /** Navigate into the editor with a freshly opened/created workspace. */
  onEnterWorkspace: (ws: Workspace) => void;
  /** Open the global settings page. */
  onOpenSettings: () => void;
  /** Open the global materials library. */
  onOpenMaterials?: () => void;
  /** Open the Factory page (app-level connections). */
  onOpenFactory?: () => void;
  /** Open the References library page. */
  onOpenReferences?: () => void;
}

/** One labelled cell of the libraries segmented group. The group container draws
 *  the border + dividers; each cell is borderless and clips to it. */
function LibSeg({
  icon,
  label,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex h-full items-center gap-1.75 pl-2.5 pr-3 text-body font-medium text-ink-2 transition-colors duration-150 hover:bg-surface-2 hover:text-ink"
    >
      {icon}
      {label}
    </button>
  );
}

/** Which management dialog is open, and for which workspace. */
type Dialog = { kind: "edit" | "delete"; ws: Workspace } | null;

/** A thumbnail entry: its data-URL/src plus the capture metadata used in sorting. */
type ThumbEntry = { src: string | null; meta?: ThumbMeta };

export default function HomeView({
  onEnterWorkspace,
  onOpenSettings,
  onOpenMaterials,
  onOpenFactory,
  onOpenReferences,
}: HomeViewProps) {
  const { config, setFlag } = useAppConfig();
  // Tear down a deleted workspace's live session (tab + per-path artifact/editor
  // caches) so recreating one at the same path doesn't resurrect its stale model.
  const { close: closeSession } = useWorkspaceSessions();

  const [workspaces, setWorkspaces] = useState<Workspace[] | null>(null); // null = loading
  const [query, setQuery] = useState(""); // local, not persisted
  const [composing, setComposing] = useState(false);
  // Path of the workspace currently being opened (card spinner), or "create".
  const [busyKey, setBusyKey] = useState<string | null>(null);
  // The open management dialog (rename/delete), plus whether its action is busy.
  const [dialog, setDialog] = useState<Dialog>(null);
  const [dialogBusy, setDialogBusy] = useState(false);
  // Active archive undo toast. Keyed by path so that archiving a second workspace
  // replaces the toast and resets the auto-dismiss timer (via `key` on the component).
  const [toast, setToast] = useState<{ ws: Workspace } | null>(null);
  // Transient error line for a failed archive/restore (auto-clears).
  const [error, setError] = useState<string | null>(null);
  // Render thumbnails keyed by workspace path.
  const [thumbs, setThumbs] = useState<Record<string, ThumbEntry>>({});
  // Active tag filter — clicking a chip on a card sets this; X pill clears it.
  const [tagFilter, setTagFilter] = useState<string | null>(null);
  // Search input, focused by the ⌘K / Ctrl+K shortcut.
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let cancelled = false;
    listWorkspaceThumbnails().then((list) => {
      if (cancelled) return;
      const map: Record<string, ThumbEntry> = {};
      for (const t of list)
        map[t.path] = {
          src: t.dataUrl,
          meta: { capturedAt: t.capturedAt, partCount: t.partCount },
        };
      setThumbs(map);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  // ⌘K / Ctrl+K focuses the search; Escape clears the query while it's focused.
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && (e.key === "k" || e.key === "K")) {
        e.preventDefault();
        searchRef.current?.focus();
        searchRef.current?.select();
      } else if (e.key === "Escape" && document.activeElement === searchRef.current) {
        setQuery("");
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  // Auto-clear the transient archive/restore error after a few seconds.
  useEffect(() => {
    if (error == null) return;
    const id = window.setTimeout(() => setError(null), 5000);
    return () => window.clearTimeout(id);
  }, [error]);

  const view = config.homeView;
  const filter = config.homeFilter;

  /** Re-read the registry into state (after a mutation). */
  const refresh = useCallback(async () => {
    const list = await listWorkspaces();
    setWorkspaces(list);
  }, []);

  useEffect(() => {
    let cancelled = false;
    listWorkspaces().then((list) => {
      if (!cancelled) setWorkspaces(list);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  // Project thumbs → the ThumbMeta map the pure selectors consume.
  const thumbMetas = useMemo(() => {
    const out: Record<string, ThumbMeta> = {};
    for (const [path, entry] of Object.entries(thumbs)) {
      if (entry.meta) out[path] = entry.meta;
    }
    return out;
  }, [thumbs]);

  const list = useMemo(() => workspaces ?? [], [workspaces]);
  const { visible, counts } = useMemo(
    () =>
      selectWorkspaces({
        workspaces: list,
        thumbs: thumbMetas,
        filter,
        query,
        tagFilter,
        now: Date.now(),
      }),
    [list, thumbMetas, filter, query, tagFilter],
  );
  const hero = useMemo(
    () => heroWorkspace({ workspaces: list, thumbs: thumbMetas, filter, query, now: Date.now() }),
    [list, thumbMetas, filter, query],
  );

  const handleOpen = useCallback(
    async (ws: Workspace) => {
      if (busyKey) return;
      setBusyKey(ws.path);
      try {
        const opened = await openWorkspace(ws.path);
        onEnterWorkspace(opened);
      } catch {
        // Open failed — drop the spinner and leave the user on the home page.
        setBusyKey(null);
      }
    },
    [busyKey, onEnterWorkspace],
  );

  /** Returns an error message to show inline, or `null` on success (navigates). */
  const handleCreate = useCallback(
    async (name: string, parentDir: string): Promise<string | null> => {
      setBusyKey("create");
      try {
        const ws = await createWorkspace(name, parentDir);
        onEnterWorkspace(ws);
        return null;
      } catch (e) {
        setBusyKey(null);
        return e instanceof Error ? e.message : String(e);
      }
    },
    [onEnterWorkspace],
  );

  /** Edit name/description/tags via dialog. Returns an inline error, or `null` on success (closes). */
  const handleEditDetails = useCallback(
    async (
      ws: Workspace,
      payload: { name: string; description: string; tags: string[] },
    ): Promise<string | null> => {
      setDialogBusy(true);
      try {
        if (payload.name.trim() && payload.name.trim() !== ws.name) {
          await acceptProposedName(ws.path, payload.name.trim());
        }
        // The dialog is a full replace, so "" legitimately means "clear it". Send the
        // string as-is (never null): a closed workspace's direct file write only
        // applies `Some(description)`, so a null would silently no-op the clear.
        await editWorkspaceDetails(ws.path, payload.description, payload.tags);
        await refresh();
        setDialog(null);
        return null;
      } catch (e) {
        return e instanceof Error ? e.message : String(e);
      } finally {
        setDialogBusy(false);
      }
    },
    [refresh],
  );

  /** Delete via dialog. Returns an inline error, or `null` on success (closes). */
  const handleDelete = useCallback(
    async (ws: Workspace, deleteFiles: boolean): Promise<string | null> => {
      setDialogBusy(true);
      try {
        await deleteWorkspace(ws.path, deleteFiles);
        // The workspace is gone: close any live tab for it AND evict its per-path
        // frontend caches (GLB bytes + editor view state). Without this, recreating
        // a workspace at the same path re-seeds the viewport from the stale cache.
        closeSession(ws.path);
        await refresh();
        setDialog(null);
        return null;
      } catch (e) {
        return e instanceof Error ? e.message : String(e);
      } finally {
        setDialogBusy(false);
      }
    },
    [refresh, closeSession],
  );

  const handleArchive = useCallback(
    async (ws: Workspace) => {
      setError(null);
      try {
        await archiveWorkspace(ws.path);
        await refresh();
        setToast({ ws });
      } catch {
        // Surface a transient error and reconcile so the card reflects reality.
        setError("Couldn't archive that workspace. Try again.");
        await refresh();
      }
    },
    [refresh],
  );

  const handleRestore = useCallback(
    async (ws: Workspace) => {
      setError(null);
      try {
        await restoreWorkspace(ws.path);
        await refresh();
      } catch {
        setError("Couldn't restore that workspace. Try again.");
        await refresh();
      }
    },
    [refresh],
  );

  const handleReveal = useCallback((ws: Workspace) => {
    // Reveal the workspace folder in the OS file manager. Best-effort: a denied
    // or unsupported reveal must not break the launcher.
    void revealItemInDir(ws.path).catch(() => {});
  }, []);

  const handleAcceptName = useCallback(
    async (ws: Workspace) => {
      if (!ws.proposedName) return;
      try {
        await acceptProposedName(ws.path, ws.proposedName);
        await refresh();
      } catch {
        /* surfaced elsewhere */
      }
    },
    [refresh],
  );

  const handleDismissName = useCallback(
    async (ws: Workspace) => {
      try {
        await dismissProposedName(ws.path);
        await refresh();
      } catch {
        /* noop */
      }
    },
    [refresh],
  );

  const loading = workspaces === null;
  const isEmpty = !loading && (workspaces?.length ?? 0) === 0;

  // The home page's global actions live in the persistent AppHeader; it has no crumb.
  useHeaderSlot({
    actions: (
      <>
        {/* Libraries — one segmented control (borders + dividers on the container). */}
        {(onOpenMaterials || onOpenFactory || onOpenReferences) && (
          <div className="flex h-8 shrink-0 items-stretch divide-x divide-line-2 overflow-hidden rounded-lg border border-line-2 bg-surface">
            {onOpenMaterials && (
              <LibSeg
                icon={<SwatchBook size={16} strokeWidth={ICON_STROKE} />}
                label="Materials"
                onClick={onOpenMaterials}
              />
            )}
            {onOpenFactory && (
              <LibSeg
                icon={<Factory size={16} strokeWidth={ICON_STROKE} />}
                label="Factory"
                onClick={onOpenFactory}
              />
            )}
            {onOpenReferences && (
              <LibSeg
                icon={<BookMarked size={16} strokeWidth={ICON_STROKE} />}
                label="References"
                onClick={onOpenReferences}
              />
            )}
          </div>
        )}

        {/* App utilities — Settings + Help as one segmented pair. */}
        <UtilityCluster onOpenSettings={onOpenSettings} />
      </>
    ),
  });

  return (
    <div className="flex min-h-0 w-full flex-1 flex-col overflow-y-auto">
      {/* Body — centered content column, wide enough for the gallery grid. */}
      <main className="mx-auto flex w-full max-w-[1140px] flex-1 flex-col gap-5 px-8 pb-16 pt-9">
        {isEmpty ? (
          // First run: just the empty-state prompt (no hero / toolbar).
          <EmptyState onCreate={() => setComposing(true)} />
        ) : (
          <>
            {hero && hero.path !== config.homeHeroDismissed && !query && !tagFilter && (
              <div className="motion-safe:animate-rise">
                <ContinueHero
                  workspace={hero}
                  thumbSrc={thumbs[hero.path]?.src ?? null}
                  onContinue={(ws) => void handleOpen(ws)}
                  onReveal={(ws) => handleReveal(ws)}
                  onClose={() => setFlag("homeHeroDismissed", hero.path)}
                />
              </div>
            )}

            <LibraryToolbar
              query={query}
              onQuery={setQuery}
              filter={filter}
              onFilter={(f) => setFlag("homeFilter", f)}
              view={view}
              onView={(v) => setFlag("homeView", v)}
              onNew={() => setComposing(true)}
              counts={counts}
              inputRef={searchRef}
              tagFilter={tagFilter}
              onClearTag={() => setTagFilter(null)}
            />

            {loading ? (
              <div
                style={{ gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))" }}
                className="grid gap-3"
              >
                {[0, 1, 2, 3].map((i) => (
                  <div
                    key={i}
                    className="aspect-[4/3] rounded-panel border border-line bg-surface/70 motion-safe:animate-pulse"
                    style={{ animationDelay: `${i * 120}ms` }}
                  />
                ))}
              </div>
            ) : visible.length === 0 ? (
              <NoResults query={query} filter={filter} onClear={() => setQuery("")} />
            ) : (
              <WorkspaceGallery
                workspaces={visible}
                view={view}
                thumbs={thumbs}
                busyKey={busyKey}
                onOpen={(ws) => void handleOpen(ws)}
                onEditDetails={(ws) => setDialog({ kind: "edit", ws })}
                onArchive={(ws) => void handleArchive(ws)}
                onRestore={(ws) => void handleRestore(ws)}
                onDelete={(ws) => setDialog({ kind: "delete", ws })}
                onAcceptName={(ws) => void handleAcceptName(ws)}
                onDismissName={(ws) => void handleDismissName(ws)}
                onTagClick={(t) => setTagFilter(t)}
              />
            )}
          </>
        )}
      </main>

      {/* Transient archive/restore error — a single dismissible danger line. */}
      {error && (
        <div
          role="alert"
          aria-live="polite"
          className="fixed bottom-20 left-1/2 z-50 flex -translate-x-1/2 items-center gap-2 rounded-lg border border-danger-line bg-danger-bg px-3.5 py-2.5 text-body text-danger shadow-float motion-safe:animate-rise"
        >
          <AlertTriangle size={15} strokeWidth={ICON_STROKE} className="shrink-0" aria-hidden />
          <span>{error}</span>
          <button
            type="button"
            aria-label="Dismiss"
            onClick={() => setError(null)}
            className="ml-1 font-semibold text-danger transition-colors duration-150 hover:text-danger-press focus-visible:outline-none focus-visible:underline"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Archive undo toast — replaces itself when a new workspace is archived. */}
      {toast && (
        <ArchiveToast
          key={toast.ws.path}
          name={toast.ws.name}
          onUndo={() => {
            void handleRestore(toast.ws);
            setToast(null);
          }}
          onDismiss={() => setToast(null)}
        />
      )}

      {/* New-workspace composer — floats over the library / empty state. */}
      {composing && (
        <NewWorkspaceDialog
          busy={busyKey === "create"}
          onCreate={handleCreate}
          onClose={() => {
            if (busyKey !== "create") setComposing(false);
          }}
        />
      )}

      {/* Management dialogs (edit / delete) */}
      {dialog?.kind === "edit" && (
        <EditDetailsDialog
          ws={dialog.ws}
          busy={dialogBusy}
          onSubmit={(p) => handleEditDetails(dialog.ws, p)}
          onClose={() => {
            if (!dialogBusy) setDialog(null);
          }}
        />
      )}
      {dialog?.kind === "delete" && (
        <DeleteDialog
          ws={dialog.ws}
          busy={dialogBusy}
          onConfirm={(deleteFiles) => handleDelete(dialog.ws, deleteFiles)}
          onClose={() => {
            if (!dialogBusy) setDialog(null);
          }}
        />
      )}
    </div>
  );
}
