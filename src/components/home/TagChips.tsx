export function TagChips({
  tags,
  max = 4,
  onTagClick,
}: {
  tags: string[];
  max?: number;
  onTagClick?: (tag: string) => void;
}) {
  if (tags.length === 0) return null;
  const shown = tags.slice(0, max);
  const extra = tags.length - shown.length;
  return (
    <div className="flex flex-wrap items-center gap-1.25">
      {shown.map((t) => {
        const cls =
          "inline-flex items-center rounded-full border border-line-2 bg-surface-2 px-2 py-0.5 text-micro font-semibold text-ink-2";
        return onTagClick ? (
          <button
            key={t}
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onTagClick(t);
            }}
            className={`${cls} transition-colors hover:border-accent-line hover:text-accent`}
          >
            {t}
          </button>
        ) : (
          <span key={t} className={cls}>
            {t}
          </span>
        );
      })}
      {extra > 0 && <span className="text-micro font-semibold text-ink-3">+{extra}</span>}
    </div>
  );
}
