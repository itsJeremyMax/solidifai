/**
 * WorkspaceStorage — the "Workspace & storage" settings section. Shows where the
 * active workspace lives on disk (project folder + exports folder) with quick
 * "open in the file manager" actions, plus its created / last-opened times.
 *
 * Settings is reachable from the launcher too (no workspace open), so this
 * degrades to a friendly hint in that case, mirroring AgentConfig.
 */
import { useEffect, useState } from "react";
import { Box, FolderOpen } from "lucide-react";

import { getExportDir, revealWorkspaceDir } from "../../lib/ipc";
import { getActiveWorkspace, relativeTime, tildePath, type Workspace } from "../../lib/workspaces";

const ICON_STROKE = 1.7;

interface Loaded {
  ws: Workspace | null;
  exportDir: string | null;
}

/** A ghost "open this folder" action. Resolves the target server-side. */
function OpenButton({ which, label }: { which: "workspace" | "exports"; label: string }) {
  return (
    <button
      type="button"
      onClick={() => void revealWorkspaceDir(which)}
      title={`Open ${label}`}
      className="inline-flex h-8 shrink-0 items-center gap-1.75 rounded-lg border border-line-2 bg-surface px-3 text-body font-medium text-ink-2 transition-colors duration-150 hover:border-line-3 hover:text-ink"
    >
      <FolderOpen size={14} strokeWidth={ICON_STROKE} />
      Open
    </button>
  );
}

/** One row: an eyebrow label over its value, with an optional trailing action. */
function Row({
  label,
  value,
  mono = false,
  action,
}: {
  label: string;
  value: string;
  mono?: boolean;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-4 px-4 py-3.5">
      <div className="min-w-0 flex-1">
        <div className="text-micro uppercase tracking-eyebrow text-ink-3">{label}</div>
        <div
          className={`mt-0.5 truncate text-ink ${mono ? "font-mono text-caption" : "text-body"}`}
        >
          {value}
        </div>
      </div>
      {action}
    </div>
  );
}

export default function WorkspaceStorage() {
  const [loaded, setLoaded] = useState<Loaded | null>(null); // null = loading

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const ws = await getActiveWorkspace();
      let exportDir: string | null = null;
      if (ws) {
        try {
          exportDir = await getExportDir();
        } catch {
          exportDir = null;
        }
      }
      if (!cancelled) setLoaded({ ws, exportDir });
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="mx-auto max-w-160 py-6.5">
      <h2 className="text-base font-bold tracking-snug text-ink">Workspace &amp; storage</h2>
      <p className="mt-1.25 text-body leading-normal text-ink-2">
        Where the active workspace lives on disk, and where exports are written.
      </p>

      {loaded === null ? (
        <div className="mt-4.5 text-body text-ink-3">Loading…</div>
      ) : loaded.ws === null ? (
        <div className="mt-4.5 rounded-panel border border-dashed border-line-2 bg-surface-2 px-4 py-4.5 text-center text-body text-ink-3">
          Open a workspace to see its location and storage.
        </div>
      ) : (
        <>
          <div className="mt-4.5 flex items-center gap-2.5">
            <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl border border-line-2 bg-surface-2 text-ink-3">
              <Box size={18} strokeWidth={1.5} />
            </span>
            <span className="truncate text-base font-semibold tracking-snug text-ink">
              {loaded.ws.name}
            </span>
          </div>

          <div className="mt-3.5 divide-y divide-line overflow-hidden rounded-panel border border-line bg-surface">
            <Row
              label="Location"
              value={tildePath(loaded.ws.path)}
              mono
              action={<OpenButton which="workspace" label="the workspace folder" />}
            />
            {loaded.exportDir && (
              <Row
                label="Exports"
                value={tildePath(loaded.exportDir)}
                mono
                action={<OpenButton which="exports" label="the exports folder" />}
              />
            )}
            <Row label="Created" value={relativeTime(loaded.ws.createdAt)} />
            <Row label="Last opened" value={relativeTime(loaded.ws.lastOpenedAt)} />
          </div>
        </>
      )}
    </div>
  );
}
