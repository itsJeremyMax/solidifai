/**
 * FactoryView — the top-level Factory page (`/factory`, and `/w/:wsPath/factory`
 * in the editor). Your production hub: the one place to turn a design into a real
 * object. It lists the connections (print destinations) you set up once and select
 * from in the editor's Make tab. Mirrors the Materials page: a grid of connections
 * plus a nested editor route ({@link ConnectionEditor}) in the `<Outlet/>`, so the
 * grid stays mounted and connection URLs are deep-linkable. The connection store is
 * app-level, so every mount shows the same list. A future managed-manufacturing
 * provider appears here as another connection, no shell change required.
 */
import { useEffect } from "react";
import { ArrowLeft, Plus } from "lucide-react";
import { Outlet, useNavigate } from "react-router-dom";

import { useFabrication } from "../../hooks/useFabrication";
import { useGoBack } from "../../hooks/useGoBack";
import { useHeaderSlot } from "../../state/headerSlot";
import { ACCENT_CTA } from "../../lib/styles";
import ConnectionCard from "./ConnectionCard";
import type { FactoryOutletContext } from "./factoryContext";
import PageIntro from "../ui/PageIntro";

const ICON_STROKE = 1.7;
const NO_MODEL = -1; // the page manages connections; estimate/orient need a model, unused here.

export default function FactoryView() {
  const navigate = useNavigate();
  const goBack = useGoBack("..");
  const fab = useFabrication(NO_MODEL);

  // Load the connection list once on mount.
  useEffect(() => {
    void fab.list();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
          <span className="font-medium text-ink-2">Factory</span>
        </div>
      </div>
    ),
    actions: (
      <button type="button" onClick={() => navigate("new")} className={`${ACCENT_CTA} h-8 px-3.25`}>
        <Plus size={15} strokeWidth={2} />
        New connection
      </button>
    ),
  });

  const outletContext: FactoryOutletContext = {
    destinations: fab.destinations,
    profiles: fab.profiles,
    fetchProfiles: fab.fetchProfiles,
    save: fab.save,
  };

  const empty = fab.destinations.length === 0;

  return (
    <div className="relative flex min-h-0 w-full flex-1 flex-col overflow-hidden bg-surface">
      <div className="relative min-h-0 flex-1 overflow-y-auto bg-[radial-gradient(120%_90%_at_50%_-10%,#fdfdfc,transparent_60%)] px-6.5 py-6.5">
        <PageIntro>
          Where your designs become real. Connect a slicer to estimate time and cost, then send
          straight to print.
        </PageIntro>
        <div className="mb-4 flex items-center gap-2.25 text-micro font-bold uppercase tracking-eyebrow text-ink-3">
          Connections
          <span className="rounded-full border border-line bg-surface-2 px-2 py-0.5 font-mono font-medium normal-case tracking-normal text-ink-3">
            {fab.destinations.length}
          </span>
        </div>

        {fab.loading && empty ? (
          <div className="grid place-items-center py-24 text-body text-ink-3">
            Loading connections...
          </div>
        ) : empty ? (
          <EmptyState onNew={() => navigate("new")} />
        ) : (
          <div className="grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-4">
            {fab.destinations.map((d) => (
              <ConnectionCard key={d.id} dest={d} onClick={() => navigate(d.id)} />
            ))}
            <AddCard onClick={() => navigate("new")} />
          </div>
        )}

        {fab.error && (
          <div className="mt-4.5 rounded-lg border border-danger-line bg-danger-bg px-3.75 py-3 font-mono text-caption text-danger">
            {fab.error}
          </div>
        )}
      </div>

      {/* Editor (nested route), rendered over the grid. */}
      <Outlet context={outletContext} />
    </div>
  );
}

/** The dashed "Add connection" tile at the end of the grid. */
function AddCard({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="group flex cursor-pointer flex-col items-center justify-center gap-2.5 rounded-[15px] border border-dashed border-line-2 bg-surface-2 px-4 py-5 text-ink-3 transition duration-200 ease-out-soft hover:-translate-y-0.5 hover:border-accent-line hover:bg-surface hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-tint"
    >
      <span className="grid h-9.5 w-9.5 place-items-center rounded-[11px] border border-current opacity-70">
        <Plus size={20} strokeWidth={1.9} />
      </span>
      <span className="text-body font-semibold">New connection</span>
    </button>
  );
}

/** Empty state. */
function EmptyState({ onNew }: { onNew: () => void }) {
  return (
    <div className="grid place-items-center gap-4 py-20 text-center">
      <p className="max-w-90 text-body text-ink-2">No connections yet. Add one to get started.</p>
      <button type="button" onClick={onNew} className={`${ACCENT_CTA} h-9.5 px-4`}>
        <Plus size={15} strokeWidth={2} />
        New connection
      </button>
    </div>
  );
}
