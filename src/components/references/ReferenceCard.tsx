import { Pencil, Trash2 } from "lucide-react";
import { openUrl } from "@tauri-apps/plugin-opener";
import type { ReferenceRow } from "../../hooks/useReferences";

const ICON_STROKE = 1.7;

/** Format one dim value (scalar or array) for the compact summary line. */
function fmtValue(v: number | number[]): string {
  if (Array.isArray(v)) return v.join(" x ");
  // Trim trailing zeros so 1.40 reads as 1.4; integers stay clean.
  return String(Number(v.toFixed(3)));
}

/** First few dims as "key 85 x 56 x 1.4 · height_max 18", capped for one line. */
function dimsSummary(dims: Record<string, number | number[]>): string {
  return Object.entries(dims)
    .slice(0, 3)
    .map(([key, v]) => `${key} ${fmtValue(v)}`)
    .join(" · ");
}

/** A short, readable host for a source URL (drops the scheme + path). */
function sourceLabel(source: string): string {
  try {
    return new URL(source).hostname.replace(/^www\./, "");
  } catch {
    return source;
  }
}

/** A YYYY-MM-DD provenance date, derived from `verified_at` (ISO) when present. */
function provenanceDate(entry: ReferenceRow): string | null {
  if (!entry.verified_at) return null;
  return entry.verified_at.slice(0, 10);
}

/** One reference entry as a row in the References list. Click to edit. */
export default function ReferenceCard({
  entry,
  onEdit,
  onDelete,
}: {
  entry: ReferenceRow;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const dims = dimsSummary(entry.dims_mm);
  const date = provenanceDate(entry);
  let provenance: string | null = null;
  if (!entry.builtin) {
    if (entry.origin === "learned") {
      provenance = entry.verified_in
        ? `learned in ${entry.verified_in}${date ? `, ${date}` : ""}`
        : `learned${date ? `, ${date}` : ""}`;
    } else {
      provenance = `added manually${date ? `, ${date}` : ""}`;
    }
  }
  const isExternal = /^https?:\/\//.test(entry.source);

  return (
    <div
      onClick={onEdit}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onEdit();
        }
      }}
      className="group flex cursor-pointer items-start gap-3.5 rounded-[15px] border border-line-2 bg-surface px-4 py-3.5 text-left shadow-card transition-[transform,border-color,box-shadow] duration-200 ease-out-soft hover:-translate-y-0.5 hover:border-accent-line hover:shadow-float focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-tint"
    >
      <div className="min-w-0 flex-1">
        {/* Primary line: id + badges + category chip */}
        <div className="flex flex-wrap items-center gap-2">
          <span className="truncate font-mono text-body font-semibold text-ink">{entry.id}</span>
          <span className="rounded-full border border-line bg-surface-2 px-2 py-0.5 text-micro font-semibold text-ink-3">
            {entry.category}
          </span>
          {entry.builtin && (
            <span className="rounded-full border border-line bg-surface-2 px-2 py-0.5 text-micro font-semibold text-ink-3">
              builtin
            </span>
          )}
          {entry.shadowsSeed && (
            <span className="rounded-full border border-accent-line bg-accent-tint px-2 py-0.5 text-micro font-semibold text-accent">
              overrides builtin
            </span>
          )}
        </div>

        {/* Dims summary */}
        {dims && <div className="mt-1 truncate font-mono text-caption text-ink-3">{dims}</div>}

        {/* Provenance + source */}
        <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-caption text-ink-3">
          {provenance && <span>{provenance}</span>}
          {entry.source &&
            (isExternal ? (
              <a
                href={entry.source}
                title={entry.source}
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  void openUrl(entry.source);
                }}
                className="inline-flex max-w-60 items-center gap-0.5 truncate text-accent transition-colors hover:text-accent-press"
              >
                <span className="truncate">{sourceLabel(entry.source)}</span>
                <span className="align-super text-[0.7em] opacity-70">↗</span>
              </a>
            ) : (
              <span className="max-w-60 truncate" title={entry.source}>
                {entry.source}
              </span>
            ))}
        </div>
      </div>

      {/* Edit + delete affordances, user entries only. */}
      {!entry.builtin && (
        <div className="flex shrink-0 items-center gap-1 opacity-0 transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100">
          <button
            type="button"
            aria-label={`Edit ${entry.id}`}
            onClick={(e) => {
              e.stopPropagation();
              onEdit();
            }}
            className="grid h-7.5 w-7.5 place-items-center rounded-lg text-ink-3 transition-colors duration-150 hover:bg-surface-2 hover:text-ink"
          >
            <Pencil size={15} strokeWidth={ICON_STROKE} />
          </button>
          <button
            type="button"
            aria-label={`Delete ${entry.id}`}
            onClick={(e) => {
              e.stopPropagation();
              onDelete();
            }}
            className="grid h-7.5 w-7.5 place-items-center rounded-lg text-ink-3 transition-colors duration-150 hover:bg-danger-bg hover:text-danger"
          >
            <Trash2 size={15} strokeWidth={ICON_STROKE} />
          </button>
        </div>
      )}
    </div>
  );
}
