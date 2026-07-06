import type { Material, MaterialLibrary } from "../../lib/materials";
import type { Scope } from "../../hooks/useMaterials";

/**
 * Data the Materials grid (the layout route) shares with its editor drawer (the
 * nested `new` / `:materialId` route) via react-router's Outlet context. The grid
 * owns the library + mutations; the drawer owns only the in-progress draft.
 */
export interface MaterialsOutletContext {
  scope: Scope;
  loading: boolean;
  library: MaterialLibrary;
  /** Global library records — used to resolve global-only materials in workspace scope. */
  globalMaterials: Material[];
  /** The effective default id (workspace own default, else inherited global default). */
  effectiveDefault: string | null;
  upsert: (m: Material) => void;
  remove: (id: string) => void;
  /** Queue an id to become the default once the library reflects it (see the grid's effect). */
  requestDefault: (id: string) => void;
}
