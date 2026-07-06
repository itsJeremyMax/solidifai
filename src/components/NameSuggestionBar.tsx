import { useState } from "react";
import { Sparkles } from "lucide-react";
import { useWorkspaceMeta } from "../hooks/useWorkspaceMeta";
import { acceptProposedName, dismissProposedName } from "../lib/workspaces";

/**
 * Inline editor-chrome bar: shows Sol's staged name proposal with Accept/Dismiss.
 * Renders nothing unless a proposal exists and differs from the current name.
 *
 * After accept/dismiss the Rust layer writes workspace.json and emits
 * `workspace-meta-updated`, which re-runs {@link useWorkspaceMeta} and clears
 * `proposedName` — so the bar auto-hides without any local state beyond `busy`.
 */
export function NameSuggestionBar({
  wsPath,
  currentName,
}: {
  wsPath: string;
  currentName: string;
}) {
  const meta = useWorkspaceMeta(wsPath);
  const [busy, setBusy] = useState(false);

  const proposed = meta?.proposedName ?? null;
  if (!proposed || proposed === currentName) return null;

  const accept = async () => {
    setBusy(true);
    try {
      await acceptProposedName(wsPath, proposed);
    } catch {
      /* surfaced elsewhere */
    } finally {
      setBusy(false);
    }
  };

  const dismiss = async () => {
    setBusy(true);
    try {
      await dismissProposedName(wsPath);
    } catch {
      /* noop */
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="flex h-9 shrink-0 items-center gap-2 border-b border-line bg-surface-2 px-3 text-caption"
      style={{
        background:
          "linear-gradient(to right, rgba(43,108,255,0.035), rgba(43,108,255,0.018) 60%, transparent)",
      }}
    >
      {/* Sol glyph */}
      <Sparkles size={12} strokeWidth={1.8} className="shrink-0 text-accent opacity-80" />

      <span className="text-ink-2">Sol suggests</span>

      <span className="font-semibold text-ink">{proposed}</span>

      <div className="flex-1" />

      <button
        type="button"
        onClick={() => void accept()}
        disabled={busy}
        className="rounded-md px-2.5 py-1 text-caption font-semibold text-accent hover:bg-accent-tint disabled:opacity-50 transition-colors duration-100"
      >
        Accept
      </button>

      <button
        type="button"
        onClick={() => void dismiss()}
        disabled={busy}
        className="rounded-md px-2.5 py-1 text-caption font-medium text-ink-3 hover:text-ink hover:bg-surface-hover disabled:opacity-50 transition-colors duration-100"
      >
        Dismiss
      </button>
    </div>
  );
}
