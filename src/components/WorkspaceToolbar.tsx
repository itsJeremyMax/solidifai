import { useState } from "react";
import { DraftingCompass, Download, Loader2, Ruler, Upload } from "lucide-react";

import ExportDialog from "./ExportDialog";
import { useDrawing } from "../hooks/useDrawing";
import { useExport } from "../hooks/useExport";
import { useImport } from "../hooks/useImport";
import { ACCENT_CTA } from "../lib/styles";

/** Shared lucide stroke weight to match the design language. */
const ICON_STROKE = 1.7;

/** A bordered surface button. `primary` renders the cobalt accent CTA. */
function BarButton({
  children,
  icon,
  primary = false,
  onClick,
  title,
}: {
  children: React.ReactNode;
  icon: React.ReactNode;
  primary?: boolean;
  onClick?: () => void;
  title?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      className={
        primary
          ? `${ACCENT_CTA} h-8 px-3`
          : "inline-flex h-8 items-center gap-1.75 rounded-lg border border-line-2 bg-surface px-3 text-body font-medium text-ink transition-colors duration-150 hover:border-line-3"
      }
    >
      <span className={primary ? "opacity-100" : "opacity-70"}>{icon}</span>
      {children}
    </button>
  );
}

/**
 * Export button — the primary cobalt CTA. Opens the full {@link ExportDialog}
 * (format rail + per-format options). Confirming runs the shared
 * {@link useExport} flow (native Save dialog + fallback + toast). A transient
 * result toast floats just under the bar.
 */
function ExportMenu() {
  const [open, setOpen] = useState(false);
  const { exporting, note, runExport } = useExport();

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen(true)}
        disabled={exporting !== null}
        className={`${ACCENT_CTA} h-8 px-3 disabled:opacity-60`}
      >
        {exporting !== null ? (
          <Loader2 className="animate-spin" size={15} strokeWidth={2.2} />
        ) : (
          <Download size={15} strokeWidth={1.8} />
        )}
        Export
      </button>

      {open && (
        <ExportDialog
          onClose={() => setOpen(false)}
          onExport={(req) => {
            setOpen(false);
            void runExport(req.formatKey, req.ext, req.options);
          }}
        />
      )}

      {/* Transient export result toast, floating just under the bar. */}
      {note && (
        <div
          className={`animate-rise absolute right-0 top-10 z-30 max-w-75 truncate rounded-lg border bg-surface px-2.75 py-1.75 font-mono text-caption shadow-float ${
            note.kind === "ok"
              ? "border-[rgba(25,169,87,.3)] text-engine"
              : "border-danger-line text-danger"
          }`}
        >
          {note.text}
        </div>
      )}
    </div>
  );
}

/**
 * Import button — brings an existing STEP/BREP/STL in as a ghosted reference
 * fixture (you fit your design around it). Mirrors the Export flow: a native file
 * picker via the shared {@link useImport}, with a transient toast under the bar.
 */
function ImportButton() {
  const { importing, note, pickAndImport } = useImport();

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => void pickAndImport()}
        disabled={importing}
        title="Import a STEP, BREP, or STL as a reference to fit around"
        className="inline-flex h-8 items-center gap-1.75 rounded-lg border border-line-2 bg-surface px-3 text-body font-medium text-ink transition-colors duration-150 hover:border-line-3 disabled:opacity-60"
      >
        {importing ? (
          <Loader2 className="animate-spin" size={15} strokeWidth={2.2} />
        ) : (
          <Upload size={15} strokeWidth={1.8} />
        )}
        Import
      </button>

      {note && (
        <div
          className={`animate-rise absolute right-0 top-10 z-30 max-w-75 truncate rounded-lg border bg-surface px-2.75 py-1.75 font-mono text-caption shadow-float ${
            note.kind === "ok"
              ? "border-[rgba(25,169,87,.3)] text-engine"
              : "border-danger-line text-danger"
          }`}
        >
          {note.text}
        </div>
      )}
    </div>
  );
}

/**
 * Drawing button — generates a 2D technical drawing (multi-view + spec sheet) of
 * the current model as PDF (+ SVG alongside) via the shared {@link useDrawing}.
 * Mirrors the Import/Export flow: a native Save dialog + a transient toast.
 */
function DrawingButton() {
  const { busy, note, createDrawing } = useDrawing();

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => void createDrawing()}
        disabled={busy}
        title="Generate a dimensioned 2D drawing + spec sheet (PDF)"
        className="inline-flex h-8 items-center gap-1.75 rounded-lg border border-line-2 bg-surface px-3 text-body font-medium text-ink transition-colors duration-150 hover:border-line-3 disabled:opacity-60"
      >
        {busy ? (
          <Loader2 className="animate-spin" size={15} strokeWidth={2.2} />
        ) : (
          <DraftingCompass size={15} strokeWidth={1.8} />
        )}
        Drawing
      </button>

      {note && (
        <div
          className={`animate-rise absolute right-0 top-10 z-30 max-w-75 truncate rounded-lg border bg-surface px-2.75 py-1.75 font-mono text-caption shadow-float ${
            note.kind === "ok"
              ? "border-[rgba(25,169,87,.3)] text-engine"
              : "border-danger-line text-danger"
          }`}
        >
          {note.text}
        </div>
      )}
    </div>
  );
}

/**
 * WorkspaceToolbar — the per-session document-verb strip that sits between the
 * global AppHeader and the 3-pane canvas. Only rendered for the ACTIVE session
 * (gated by `{active && …}` in AppShell), so its actions always target the
 * focused workspace.
 *
 * Left: scope label — the workspace name (engine version lives in the header pill).
 * Right: Measure / Import / Drawing / Export.
 */
export default function WorkspaceToolbar({ workspaceName }: { workspaceName: string | null }) {
  return (
    <div className="flex h-11 shrink-0 items-center gap-2 border-b border-line bg-surface-2 px-3">
      {/* Scope label: workspace name (engine version is shown in the header pill) */}
      <div className="flex min-w-0 items-center text-body">
        <span className="truncate font-medium text-ink-2">{workspaceName ?? "Workspace"}</span>
      </div>

      <div className="flex-1" />

      {/* Document verbs — act on the focused model */}
      <div className="flex items-center gap-2">
        <BarButton icon={<Ruler size={15} strokeWidth={ICON_STROKE} />}>Measure</BarButton>
        <ImportButton />
        <DrawingButton />
        <ExportMenu />
      </div>
    </div>
  );
}
