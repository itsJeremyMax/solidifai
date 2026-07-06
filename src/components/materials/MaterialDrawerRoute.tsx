/**
 * MaterialDrawerRoute — the material editor drawer as a nested route
 * (`materials/new` and `materials/:materialId`). It renders inside the Materials
 * grid's `<Outlet/>`, so the grid stays mounted behind it and the URL is
 * deep-linkable. The drawer owns only the in-progress draft; library data +
 * mutations come from the grid via Outlet context.
 */
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useOutletContext, useParams } from "react-router-dom";

import type { Material } from "../../lib/materials";
import { useGoBack } from "../../hooks/useGoBack";
import MaterialEditor, { slugify } from "./MaterialEditor";
import MaterialPreviewCard from "./MaterialPreviewCard";
import { MAT_COPY } from "./copy";
import type { MaterialsOutletContext } from "./materialsContext";

/** A blank material seeded for the "New material" drawer. */
function freshDraft(): Material {
  return { id: "", label: "", base: "pla", colorHex: "#BCBFC4", finish: "matte" };
}

export default function MaterialDrawerRoute() {
  const navigate = useNavigate();
  const { materialId } = useParams();
  const ctx = useOutletContext<MaterialsOutletContext>();

  const isNew = materialId === undefined;
  const close = useGoBack("..", { replace: true });

  // The material being edited, resolved from the workspace library or (in
  // workspace scope) the global library. Null while still loading or if missing.
  const original = useMemo<Material | null>(() => {
    if (isNew) return null;
    return (
      ctx.library.materials.find((m) => m.id === materialId) ??
      ctx.globalMaterials.find((m) => m.id === materialId) ??
      null
    );
  }, [isNew, materialId, ctx.library.materials, ctx.globalMaterials]);

  const [draft, setDraft] = useState<Material | null>(isNew ? freshDraft() : original);

  // Deep link: the library may load after mount — sync the draft once it resolves.
  useEffect(() => {
    if (isNew || draft) return;
    if (original) setDraft(original);
  }, [isNew, original, draft]);

  // Stale deep link: editing an id that does not exist once data has loaded.
  useEffect(() => {
    if (isNew || ctx.loading || original) return;
    navigate("..", { replace: true });
  }, [isNew, ctx.loading, original, navigate]);

  if (!draft) return null;

  // A global-origin material not yet in the workspace library: the drawer offers
  // "Pin to workspace" instead of Save / Set default. (Workspace scope only.)
  const pinning =
    ctx.scope === "workspace" && !isNew && !ctx.library.materials.some((m) => m.id === draft.id);

  const handleSave = () => {
    const id = isNew ? slugify(draft.label) : draft.id;
    ctx.upsert({ ...draft, id });
    close();
  };

  // Pin a global-origin material into the active workspace (idempotent upsert by id).
  const handlePin = () => {
    ctx.upsert({ ...draft });
    close();
  };

  // The editor fires onSave() then onSetDefault(); onSave persists + closes, this
  // queues the promotion to land once the library reflects the saved material.
  const handleSetDefault = () => {
    const id = isNew ? slugify(draft.label) : draft.id;
    ctx.requestDefault(id);
  };

  const handleDelete = () => {
    if (isNew) return;
    ctx.remove(draft.id);
    close();
  };

  const deleteBlockedReason = (() => {
    if (isNew) return undefined;
    if (ctx.library.materials.length <= 1) return MAT_COPY.cannotDeleteLast;
    if (draft.id === ctx.library.default) return MAT_COPY.cannotDeleteDefault;
    return undefined;
  })();

  const draftIsDefault = !isNew && draft.id === ctx.effectiveDefault;

  return (
    <>
      {/* Floating live preview, to the left of the drawer on wide windows. */}
      <div className="pointer-events-none absolute right-[370px] top-19 z-30 hidden min-[900px]:block">
        <div className="pointer-events-auto">
          <MaterialPreviewCard material={draft} />
        </div>
      </div>

      <MaterialEditor
        draft={draft}
        isNew={isNew}
        scope={ctx.scope}
        pinning={pinning}
        isDefault={draftIsDefault}
        onChange={setDraft}
        onSave={handleSave}
        onSetDefault={handleSetDefault}
        onPin={handlePin}
        onDelete={handleDelete}
        onClose={close}
        deleteBlockedReason={deleteBlockedReason}
      />
    </>
  );
}
