import { Box, Plus } from "lucide-react";
import { ACCENT_CTA } from "../../lib/styles";

const ICON_STROKE = 1.7;

export function EmptyState({ onCreate }: { onCreate: () => void }) {
  return (
    <div className="flex flex-col items-center rounded-panel border border-dashed border-line-2 bg-surface/60 px-6 py-13 text-center motion-safe:animate-rise">
      <span className="mb-4.5 grid h-14.5 w-14.5 place-items-center rounded-2xl border border-line-2 bg-surface text-accent shadow-card motion-safe:animate-floaty">
        <Box size={28} strokeWidth={1.5} />
      </span>
      <h2 className="mb-1.5 text-lg font-semibold tracking-snug text-ink">
        Create your first workspace
      </h2>
      <p className="mb-5.5 max-w-85 text-body leading-normal text-ink-2">
        A workspace is a project folder where the agent models, renders, and exports your parts.
      </p>
      <button
        type="button"
        onClick={onCreate}
        className={`${ACCENT_CTA} h-9.5 px-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-line focus-visible:ring-offset-1`}
      >
        <Plus size={15} strokeWidth={ICON_STROKE} />
        New workspace
      </button>
    </div>
  );
}
