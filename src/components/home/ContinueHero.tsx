import { ArrowRight, FolderOpen, X } from "lucide-react";
import { ACCENT_CTA } from "../../lib/styles";
import { relativeTime, type Workspace } from "../../lib/workspaces";
import { WorkspaceThumb } from "./WorkspaceThumb";
import { TagChips } from "./TagChips";

interface ContinueHeroProps {
  workspace: Workspace;
  thumbSrc: string | null;
  onContinue: (ws: Workspace) => void;
  onReveal: (ws: Workspace) => void;
  /** Dismiss the hero (the workspace stays in the gallery below). */
  onClose: () => void;
}

export function ContinueHero({
  workspace,
  thumbSrc,
  onContinue,
  onReveal,
  onClose,
}: ContinueHeroProps) {
  return (
    <div className="bg-surface border border-line-2 rounded-panel shadow-card flex overflow-hidden relative">
      {/* Dismiss — the workspace remains in the gallery; the hero re-appears when a
          different workspace becomes the most recent. */}
      <button
        type="button"
        onClick={onClose}
        aria-label="Dismiss"
        title="Dismiss"
        className="absolute right-3 top-3 z-10 grid h-7 w-7 place-items-center rounded-lg text-ink-3 transition-colors duration-150 hover:bg-surface-2 hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-line"
      >
        <X size={15} strokeWidth={2} aria-hidden />
      </button>

      {/* Left: render thumbnail — fixed width, full panel height */}
      <WorkspaceThumb
        name={workspace.name}
        src={thumbSrc}
        className="w-[300px] shrink-0 aspect-[4/3]"
      />

      {/* Right: text column (pr-12 reserves room for the dismiss button) */}
      <div className="flex flex-1 min-w-0 flex-col py-5 pl-6 pr-12">
        {/* Eyebrow */}
        <span className="text-accent text-micro font-bold uppercase tracking-eyebrow">
          Continue where you left off
        </span>

        {/* Workspace name — the single justified one-off (largest type on the page) */}
        <h2
          className="text-ink font-bold tracking-snug truncate mt-2.5"
          style={{ fontSize: "1.9rem", lineHeight: 1.1 }}
        >
          {workspace.name}
        </h2>

        {/* Description + tags */}
        {workspace.description && (
          <p className="mt-2 line-clamp-3 text-body leading-relaxed text-ink-2">
            {workspace.description}
          </p>
        )}
        {workspace.tags.length > 0 && (
          <div className="mt-2">
            <TagChips tags={workspace.tags} />
          </div>
        )}

        {/* Last edited */}
        <p className="text-ink-3 text-body mt-2.5">Edited {relativeTime(workspace.lastOpenedAt)}</p>

        {/* Actions — push to bottom */}
        <div className="flex items-center gap-2.5 mt-auto pt-6">
          <button
            type="button"
            className={`${ACCENT_CTA} h-8 px-3.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-line focus-visible:ring-offset-1`}
            onClick={() => onContinue(workspace)}
          >
            Continue
            <ArrowRight size={13} strokeWidth={2.25} aria-hidden />
          </button>

          <button
            type="button"
            className="inline-flex items-center gap-1.5 h-8 px-3.5 rounded-lg border border-line-2 bg-surface text-body text-ink-2 font-medium transition-colors duration-150 hover:border-line-3 hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-line"
            onClick={() => onReveal(workspace)}
          >
            <FolderOpen size={13} strokeWidth={2} aria-hidden />
            Reveal in Finder
          </button>
        </div>
      </div>
    </div>
  );
}
