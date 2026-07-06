/**
 * ReferencesView — the top-level References library page (`/references`, and
 * `/w/:wsPath/references` in the editor). Verified part dimensions Sol has
 * learned, plus the builtin seed. Mirrors the Factory page: a searchable list of
 * entries plus a nested editor route ({@link ReferenceEditor}) in the
 * `<Outlet/>`, so the list stays mounted and entry URLs are deep-linkable. The
 * library is served natively (seed + user), so every mount shows the same set.
 */
import { useMemo, useState } from "react";
import { ArrowLeft, Plus, Search, Trash2 } from "lucide-react";
import { Outlet, useNavigate } from "react-router-dom";

import { useReferences, type ReferenceRow } from "../../hooks/useReferences";
import { useGoBack } from "../../hooks/useGoBack";
import { useDismiss } from "../../hooks/useDismiss";
import { useHeaderSlot } from "../../state/headerSlot";
import { ACCENT_CTA } from "../../lib/styles";
import PageIntro from "../ui/PageIntro";
import ReferenceCard from "./ReferenceCard";
import type { ReferencesOutletContext } from "./referencesContext";

const ICON_STROKE = 1.7;

/** Case-insensitive match over id, aliases, and category. */
function matches(entry: ReferenceRow, q: string): boolean {
  if (!q) return true;
  const needle = q.toLowerCase();
  if (entry.id.toLowerCase().includes(needle)) return true;
  if (entry.category.toLowerCase().includes(needle)) return true;
  return (entry.aliases ?? []).some((a) => a.toLowerCase().includes(needle));
}

export default function ReferencesView() {
  const navigate = useNavigate();
  const goBack = useGoBack("..");
  const { entries, error, save, remove } = useReferences();
  const [query, setQuery] = useState("");
  // The user entry queued for deletion (its confirm dialog is open), or null.
  const [pendingDelete, setPendingDelete] = useState<ReferenceRow | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  useHeaderSlot({
    crumb: (
      <div className="flex items-center gap-3.5">
        <button
          type="button"
          onClick={goBack}
          className="inline-flex h-8 items-center gap-1.75 rounded-lg border border-line-2 bg-surface pl-2 pr-3 text-body font-medium text-ink transition-colors duration-150 hover:border-line-3"
        >
          <ArrowLeft className="opacity-70" size={16} strokeWidth={ICON_STROKE} />
          Back
        </button>
        <div className="flex items-center gap-2 text-body text-ink-3">
          <span className="opacity-50">/</span>
          <span className="font-medium text-ink-2">References</span>
        </div>
      </div>
    ),
    actions: (
      <button type="button" onClick={() => navigate("new")} className={`${ACCENT_CTA} h-8 px-3.25`}>
        <Plus size={15} strokeWidth={2} />
        Add entry
      </button>
    ),
  });

  const filtered = useMemo(() => entries.filter((e) => matches(e, query)), [entries, query]);

  const outletContext: ReferencesOutletContext = { entries, save, remove };

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    try {
      await remove(pendingDelete.id);
      setPendingDelete(null);
      setDeleteError(null);
    } catch (e) {
      setDeleteError(String(e));
    }
  };

  const empty = entries.length === 0;
  const noResults = !empty && filtered.length === 0;

  return (
    <div className="relative flex min-h-0 w-full flex-1 flex-col overflow-hidden bg-surface">
      <div className="relative min-h-0 flex-1 overflow-y-auto bg-[radial-gradient(120%_90%_at_50%_-10%,#fdfdfc,transparent_60%)] px-6.5 py-6.5">
        <PageIntro>
          Verified part dimensions Sol has learned, plus the builtin seed. Search by name, alias, or
          category.
        </PageIntro>

        {/* Search + count */}
        <div className="mb-4 flex items-center gap-3">
          <div className="flex h-9.5 w-80 shrink-0 items-center gap-2.5 rounded-[11px] border border-line-2 bg-surface px-3.25 shadow-[0_1px_2px_rgba(16,18,24,.04)] focus-within:border-accent-line focus-within:ring-2 focus-within:ring-accent-tint">
            <Search size={15} strokeWidth={2} className="shrink-0 text-ink-3" aria-hidden />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search references"
              aria-label="Search references"
              autoComplete="off"
              spellCheck={false}
              className="min-w-0 flex-1 bg-transparent text-body text-ink placeholder:text-ink-3 focus:outline-none"
            />
          </div>
          <span className="flex items-center gap-2.25 text-micro font-bold uppercase tracking-eyebrow text-ink-3">
            Entries
            <span className="rounded-full border border-line bg-surface-2 px-2 py-0.5 font-mono font-medium normal-case tracking-normal text-ink-3">
              {filtered.length}
            </span>
          </span>
        </div>

        {empty ? (
          <EmptyState onNew={() => navigate("new")} />
        ) : noResults ? (
          <div className="grid place-items-center py-20 text-center text-body text-ink-3">
            No references match &ldquo;{query}&rdquo;.
          </div>
        ) : (
          <div className="flex flex-col gap-2.5">
            {filtered.map((e) => (
              <ReferenceCard
                key={e.id}
                entry={e}
                onEdit={() => navigate(encodeURIComponent(e.id))}
                onDelete={() => {
                  setDeleteError(null);
                  setPendingDelete(e);
                }}
              />
            ))}
          </div>
        )}

        {error && (
          <div className="mt-4.5 rounded-lg border border-danger-line bg-danger-bg px-3.75 py-3 font-mono text-caption text-danger">
            {error}
          </div>
        )}
      </div>

      {/* Editor (nested route), rendered over the list. */}
      <Outlet context={outletContext} />

      {pendingDelete && (
        <DeleteConfirm
          name={pendingDelete.id}
          error={deleteError}
          onCancel={() => {
            setPendingDelete(null);
            setDeleteError(null);
          }}
          onConfirm={() => void confirmDelete()}
        />
      )}
    </div>
  );
}

/** Empty state when there are no entries at all. */
function EmptyState({ onNew }: { onNew: () => void }) {
  return (
    <div className="grid place-items-center gap-4 py-20 text-center">
      <p className="max-w-90 text-body text-ink-2">
        No references yet. Add one, or let Sol learn dimensions as you build.
      </p>
      <button type="button" onClick={onNew} className={`${ACCENT_CTA} h-9.5 px-4`}>
        <Plus size={15} strokeWidth={2} />
        Add entry
      </button>
    </div>
  );
}

/** Destructive confirm for removing a user entry, mirroring the Factory pattern. */
function DeleteConfirm({
  name,
  error,
  onCancel,
  onConfirm,
}: {
  name: string;
  error: string | null;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const ref = useDismiss<HTMLDivElement>(true, onCancel);
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-[rgba(18,20,28,.34)] px-5 backdrop-blur-xs">
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-labelledby="reference-delete-title"
        className="animate-rise w-full max-w-105 rounded-panel border border-line-2 bg-surface p-5 shadow-float"
      >
        <div className="mb-3.5 flex items-center gap-2.5">
          <span className="grid h-8.5 w-8.5 shrink-0 place-items-center rounded-xl border border-danger-line bg-danger-bg text-danger">
            <Trash2 size={17} strokeWidth={ICON_STROKE} />
          </span>
          <h2 id="reference-delete-title" className="text-base font-bold tracking-snug text-ink">
            Delete reference
          </h2>
        </div>

        <p className="mb-4.5 text-body leading-normal text-ink-2">
          Delete <span className="font-mono font-semibold text-ink">{name}</span> from your
          references? This cannot be undone.
        </p>

        {error && (
          <div className="mb-3.5 rounded-lg border border-danger-line bg-danger-bg px-3.5 py-2.5 font-mono text-caption text-danger">
            {error}
          </div>
        )}

        <div className="flex items-center justify-end gap-2.25">
          <button
            type="button"
            onClick={onCancel}
            className="inline-flex h-9 items-center rounded-lg px-3.5 text-body font-medium text-ink-2 transition-colors duration-150 hover:bg-surface-2 hover:text-ink"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className="inline-flex h-9 items-center gap-1.75 rounded-lg border border-transparent bg-danger px-4 text-body font-medium text-white shadow-[0_1px_1px_rgba(160,30,34,.4),inset_0_1px_0_rgba(255,255,255,.2)] transition-colors duration-150 hover:bg-danger-press"
          >
            <Trash2 size={14} strokeWidth={ICON_STROKE} />
            Delete
          </button>
        </div>
      </div>
    </div>
  );
}
