/**
 * MaterialsView — the Materials library page (the `/materials` route, and
 * `/w/:wsPath/materials` in workspace scope). It owns the shade-ball grid and the
 * library data; the editor drawer is a nested route ({@link MaterialDrawerRoute})
 * rendered in the `<Outlet/>`, so the grid stays mounted and material URLs are
 * deep-linkable. Scope is positional (from the route), not an in-view toggle: in
 * workspace scope the grid already surfaces global materials as inherited
 * read-only cards, so there is nothing to toggle.
 *
 * Page chrome is published into the persistent AppHeader. All copy comes from
 * MAT_COPY (no em dashes).
 */
import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, Globe, Plus } from "lucide-react";
import { Outlet, useNavigate, useParams } from "react-router-dom";

import type { Material } from "../../lib/materials";
import { useHeaderSlot } from "../../state/headerSlot";
import { useMaterials, type Scope } from "../../hooks/useMaterials";
import { useGoBack } from "../../hooks/useGoBack";
import { getGlobalMaterials } from "../../lib/materials";
import { ACCENT_CTA } from "../../lib/styles";
import MaterialCard, { type CardOrigin } from "./MaterialCard";
import { MAT_COPY } from "./copy";
import type { MaterialsOutletContext } from "./materialsContext";
import PageIntro from "../ui/PageIntro";

const ICON_STROKE = 1.7;

interface MaterialsViewProps {
  /** Scope, fixed by the route: `/materials` is global, `/w/:wsPath/materials` is workspace. */
  scope: Scope;
  /** Active workspace name (workspace scope only); used for the section label. */
  workspaceName: string | null;
}

export default function MaterialsView({ scope, workspaceName }: MaterialsViewProps) {
  const navigate = useNavigate();
  const goBack = useGoBack("..");
  const { materialId } = useParams();

  const { library, loading, upsert, remove, setDefault } = useMaterials(scope);

  // The global library is needed in workspace scope: its default tells us which
  // card is effective when the workspace inherits, and its records let us surface
  // global-only materials read-only.
  const [globalDefault, setGlobalDefault] = useState<string | null>(null);
  const [globalMaterials, setGlobalMaterials_] = useState<Material[]>([]);
  useEffect(() => {
    let live = true;
    getGlobalMaterials().then((lib) => {
      if (!live) return;
      setGlobalDefault(lib.default);
      setGlobalMaterials_(lib.materials);
    });
    return () => {
      live = false;
    };
  }, [scope]);
  const globalIds = useMemo(() => new Set(globalMaterials.map((m) => m.id)), [globalMaterials]);

  // In workspace scope the displayed set is the workspace library plus the
  // global-only materials (read-only, available). In global scope it is just the
  // library.
  const cards = useMemo<{ material: Material; origin?: CardOrigin }[]>(() => {
    if (scope === "global") {
      return library.materials.map((m) => ({ material: m }));
    }
    const wsIds = new Set(library.materials.map((m) => m.id));
    const own = library.materials.map<{ material: Material; origin: CardOrigin }>((m) => ({
      material: m,
      origin: globalIds.has(m.id) ? "pinned" : "local",
    }));
    const inherited = globalMaterials
      .filter((m) => !wsIds.has(m.id))
      .map<{ material: Material; origin: CardOrigin }>((m) => ({ material: m, origin: "global" }));
    return [...own, ...inherited];
  }, [scope, library.materials, globalIds, globalMaterials]);

  const effectiveDefault =
    scope === "workspace" ? (library.default ?? globalDefault) : library.default;

  // The editor's "Set as default" promotes after save: record the id and apply it
  // from this effect once the saved material is present in `library` (a fresh,
  // correct setDefault closure), so it never clobbers the same-tick upsert.
  const [pendingDefault, setPendingDefault] = useState<string | null>(null);
  useEffect(() => {
    if (pendingDefault == null) return;
    if (library.materials.some((m) => m.id === pendingDefault)) {
      if (library.default !== pendingDefault) setDefault(pendingDefault);
      setPendingDefault(null);
    }
  }, [pendingDefault, library, setDefault]);

  // Page chrome: Back + "/ Materials" crumb; New CTA opens the new-material route.
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
          <span className="font-medium text-ink-2">{MAT_COPY.title}</span>
        </div>
      </div>
    ),
    actions: (
      <button type="button" onClick={() => navigate("new")} className={`${ACCENT_CTA} h-8 px-3.25`}>
        <Plus size={15} strokeWidth={2} />
        {MAT_COPY.newMaterial}
      </button>
    ),
  });

  const outletContext: MaterialsOutletContext = {
    scope,
    loading,
    library,
    globalMaterials,
    effectiveDefault,
    upsert,
    remove,
    requestDefault: setPendingDefault,
  };

  const sectionLabel =
    scope === "workspace" && workspaceName ? MAT_COPY.scopeWorkspacePrefix : MAT_COPY.countLabel;
  const sectionCount =
    scope === "workspace" && workspaceName ? workspaceName : String(cards.length);

  return (
    <div className="relative flex min-h-0 w-full flex-1 flex-col overflow-hidden bg-surface">
      {/* ── body ── */}
      <div className="relative min-h-0 flex-1 overflow-y-auto bg-[radial-gradient(120%_90%_at_50%_-10%,#fdfdfc,transparent_60%)] px-6.5 py-6.5">
        <PageIntro>{MAT_COPY.description}</PageIntro>
        <div className="mb-4 flex items-center gap-2.25 text-micro font-bold uppercase tracking-eyebrow text-ink-3">
          {sectionLabel}
          <span className="rounded-full border border-line bg-surface-2 px-2 py-0.5 font-mono font-medium normal-case tracking-normal text-ink-3">
            {sectionCount}
          </span>
        </div>

        {loading ? (
          <div className="grid place-items-center py-24 text-body text-ink-3">
            {MAT_COPY.loading}
          </div>
        ) : cards.length === 0 ? (
          <EmptyState onNew={() => navigate("new")} />
        ) : (
          <div className="grid grid-cols-[repeat(auto-fill,minmax(168px,1fr))] gap-4">
            {cards.map(({ material, origin }) => (
              <MaterialCard
                key={`${origin ?? "g"}:${material.id}`}
                material={material}
                isDefault={material.id === effectiveDefault}
                origin={origin}
                selected={material.id === materialId}
                onClick={() => navigate(material.id)}
              />
            ))}
            <AddCard
              label={scope === "workspace" ? MAT_COPY.addLocal : MAT_COPY.newMaterial}
              onClick={() => navigate("new")}
            />
          </div>
        )}

        {/* inherit-default hint (workspace scope, no own default set) */}
        {scope === "workspace" && workspaceName && !loading && library.default === null && (
          <div className="mt-4.5 flex items-start gap-2.75 rounded-[11px] border border-line bg-surface-2 px-3.75 py-3.25 text-caption leading-relaxed text-ink-2">
            <span className="grid h-5.5 w-5.5 flex-none place-items-center rounded-md bg-accent-tint text-accent">
              <Globe size={13} strokeWidth={2} />
            </span>
            <div>{MAT_COPY.inheritDefault}</div>
          </div>
        )}
      </div>

      {/* Editor drawer (nested route), rendered over the grid. */}
      <Outlet context={outletContext} />
    </div>
  );
}

/** The dashed "Add material" tile at the end of the grid. */
function AddCard({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="group flex cursor-pointer flex-col items-center justify-center gap-2.5 rounded-[15px] border border-dashed border-line-2 bg-surface-2 px-4 py-5 text-ink-3 transition duration-200 ease-out-soft hover:-translate-y-0.5 hover:border-accent-line hover:bg-surface hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-tint"
    >
      <span className="grid h-9.5 w-9.5 place-items-center rounded-[11px] border border-current opacity-70">
        <Plus size={20} strokeWidth={1.9} />
      </span>
      <span className="text-body font-semibold">{label}</span>
    </button>
  );
}

/** Empty-library state. */
function EmptyState({ onNew }: { onNew: () => void }) {
  return (
    <div className="grid place-items-center gap-4 py-20 text-center">
      <p className="text-body text-ink-2">{MAT_COPY.emptyGlobal}</p>
      <button type="button" onClick={onNew} className={`${ACCENT_CTA} h-8 px-3.25`}>
        <Plus size={15} strokeWidth={2} />
        {MAT_COPY.newMaterial}
      </button>
    </div>
  );
}
