import { useCallback, useEffect, useState } from "react";
import { FolderOpen, Plus } from "lucide-react";
import { defaultWorkspaceDir, pickDirectory, tildePath } from "../../lib/workspaces";
import Spinner from "../ui/Spinner";
import { ACCENT_CTA } from "../../lib/styles";
import { ModalShell } from "./ModalShell";

const ICON_STROKE = 1.7;

/** New-workspace dialog — name + location, then create and open the editor. */
export function NewWorkspaceDialog({
  busy,
  onCreate,
  onClose,
}: {
  busy: boolean;
  onCreate: (name: string, parentDir: string) => Promise<string | null>;
  onClose: () => void;
}) {
  const [name, setName] = useState("");
  const [parentDir, setParentDir] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Seed the location with the cross-platform default (<Documents>/Solidifai/workspaces,
  // or the last-used dir). On failure parentDir stays null → today's manual-pick flow.
  useEffect(() => {
    let cancelled = false;
    defaultWorkspaceDir().then((dir) => {
      if (!cancelled && dir) setParentDir(dir);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const trimmed = name.trim();
  const canCreate = trimmed.length > 0 && parentDir !== null && !busy;

  const choose = useCallback(async () => {
    const picked = await pickDirectory();
    if (picked) {
      setParentDir(picked);
      setError(null);
    }
  }, []);

  const submit = useCallback(async () => {
    setError(null);
    if (trimmed.length === 0) {
      setError("Enter a workspace name.");
      return;
    }
    if (parentDir === null) {
      setError("Choose a location for the workspace.");
      return;
    }
    const err = await onCreate(trimmed, parentDir);
    if (err) setError(err);
  }, [trimmed, parentDir, onCreate]);

  return (
    <ModalShell onClose={onClose} labelledBy="new-workspace-title">
      <div className="mb-3.5 flex items-center gap-2.5">
        <span className="grid h-8.5 w-8.5 shrink-0 place-items-center rounded-xl border border-line-2 bg-surface-2 text-accent">
          <Plus size={17} strokeWidth={ICON_STROKE} />
        </span>
        <h2 id="new-workspace-title" className="text-base font-bold tracking-snug text-ink">
          New workspace
        </h2>
      </div>

      {/* Name */}
      <label className="mb-3.5 block">
        <span className="mb-1.5 block text-micro font-bold uppercase tracking-eyebrow text-ink-3">
          Name
        </span>
        <input
          type="text"
          value={name}
          autoFocus
          spellCheck={false}
          placeholder="fidget-bracket"
          onChange={(e) => {
            setName(e.target.value);
            if (error) setError(null);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && canCreate) void submit();
          }}
          className="h-9.5 w-full rounded-lg border border-line-2 bg-surface-2 px-3 text-sm text-ink outline-none transition-colors duration-150 placeholder:text-ink-3 focus:border-accent focus:bg-surface focus:ring-2 focus:ring-accent-tint"
        />
      </label>

      {/* Location */}
      <div className="mb-4.5">
        <span className="mb-1.5 block text-micro font-bold uppercase tracking-eyebrow text-ink-3">
          Location
        </span>
        <div className="flex items-center gap-2.5">
          <div className="flex h-9.5 min-w-0 flex-1 items-center rounded-lg border border-line bg-surface-2 px-3">
            <span
              className={`truncate font-mono text-xs ${parentDir ? "text-ink-2" : "text-ink-3"}`}
            >
              {parentDir ? `${tildePath(parentDir)}/${trimmed || "…"}` : "No location chosen"}
            </span>
          </div>
          <button
            type="button"
            onClick={() => void choose()}
            disabled={busy}
            className="inline-flex h-9.5 shrink-0 items-center gap-1.75 rounded-lg border border-line-2 bg-surface px-3.5 text-body font-medium text-ink transition-colors duration-150 hover:border-line-3 disabled:opacity-50"
          >
            <FolderOpen className="opacity-70" size={15} strokeWidth={ICON_STROKE} />
            Change…
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-3.5 rounded-lg border border-danger-line bg-danger-bg px-3 py-2.25 font-mono text-caption text-danger">
          {error}
        </div>
      )}

      <div className="flex items-center justify-end gap-2.25">
        <button
          type="button"
          onClick={onClose}
          disabled={busy}
          className="inline-flex h-9 items-center rounded-lg px-3.5 text-body font-medium text-ink-2 transition-colors duration-150 hover:bg-surface-2 hover:text-ink disabled:opacity-50"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={() => void submit()}
          disabled={!canCreate}
          className={`${ACCENT_CTA} h-9 px-4 disabled:opacity-45 disabled:hover:bg-accent`}
        >
          {busy ? <Spinner /> : <Plus size={15} strokeWidth={ICON_STROKE} />}
          {busy ? "Creating…" : "Create workspace"}
        </button>
      </div>
    </ModalShell>
  );
}
