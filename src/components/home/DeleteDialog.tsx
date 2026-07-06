import { useCallback, useState } from "react";
import { AlertTriangle, Trash2 } from "lucide-react";
import { tildePath, type Workspace } from "../../lib/workspaces";
import Spinner from "../ui/Spinner";
import { ModalShell } from "./ModalShell";

const ICON_STROKE = 1.7;

/** Delete confirmation dialog — name + path, optional folder deletion. */
export function DeleteDialog({
  ws,
  busy,
  onConfirm,
  onClose,
}: {
  ws: Workspace;
  busy: boolean;
  onConfirm: (deleteFiles: boolean) => Promise<string | null>;
  onClose: () => void;
}) {
  const [deleteFiles, setDeleteFiles] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const confirm = useCallback(async () => {
    const err = await onConfirm(deleteFiles);
    if (err) setError(err);
  }, [deleteFiles, onConfirm]);

  return (
    <ModalShell onClose={onClose} labelledBy="delete-title">
      <div className="mb-3.5 flex items-center gap-2.5">
        <span className="grid h-8.5 w-8.5 shrink-0 place-items-center rounded-xl border border-danger-line bg-danger-bg text-danger">
          <Trash2 size={17} strokeWidth={ICON_STROKE} />
        </span>
        <h2 id="delete-title" className="text-base font-bold tracking-snug text-ink">
          Delete workspace
        </h2>
      </div>

      <p className="mb-3 text-body leading-normal text-ink-2">
        Remove <span className="font-semibold text-ink">{ws.name}</span> from your workspaces?
      </p>
      <p className="mb-4 truncate rounded-lg border border-line bg-surface-2 px-3 py-2 font-mono text-caption text-ink-3">
        {tildePath(ws.path)}
      </p>

      {/* Destructive opt-in — default OFF. */}
      <label className="mb-1 flex cursor-pointer items-start gap-2.5 rounded-xl border border-line-2 bg-surface-2 px-3 py-2.5">
        <input
          type="checkbox"
          checked={deleteFiles}
          onChange={(e) => setDeleteFiles(e.target.checked)}
          className="mt-0.5 h-3.75 w-3.75 shrink-0 accent-danger"
        />
        <span className="flex flex-col gap-0.5">
          <span className="text-body font-medium text-ink">Also delete the folder from disk</span>
          <span className="text-caption leading-[1.45] text-ink-3">
            Permanently removes the workspace directory and all its files.
          </span>
        </span>
      </label>

      {deleteFiles && (
        <div className="mb-0.5 mt-2.5 flex items-start gap-2 rounded-lg border border-danger-line bg-danger-bg px-3 py-2.25 text-caption leading-[1.45] text-danger">
          <AlertTriangle className="mt-0.25 shrink-0" size={15} strokeWidth={ICON_STROKE} />
          <span>This permanently deletes the folder and cannot be undone.</span>
        </div>
      )}

      {error && (
        <div className="mt-3 rounded-lg border border-danger-line bg-danger-bg px-3 py-2.25 font-mono text-caption text-danger">
          {error}
        </div>
      )}

      <div className="mt-4.5 flex items-center justify-end gap-2.25">
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
          onClick={() => void confirm()}
          disabled={busy}
          className="inline-flex h-9 items-center gap-1.75 rounded-lg border border-transparent bg-danger px-4 text-body font-medium text-white shadow-[0_1px_1px_rgba(160,30,34,.4),inset_0_1px_0_rgba(255,255,255,.2)] transition-colors duration-150 hover:bg-danger-press disabled:opacity-50"
        >
          {busy ? <Spinner /> : <Trash2 size={14} strokeWidth={ICON_STROKE} />}
          {busy ? "Deleting…" : deleteFiles ? "Delete + remove files" : "Delete"}
        </button>
      </div>
    </ModalShell>
  );
}
