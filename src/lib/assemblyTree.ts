/**
 * Pure assembly-tree helpers. Phase 2A renders each leaf object with a stable
 * slash-separated path id (e.g. "hinge/pin"), so the assembly hierarchy is
 * fully derivable client-side by splitting ids on "/". No engine call needed.
 *
 * No React here: these are unit-tested in assemblyTree.test.ts and reused by
 * the AssemblyTree component and the viewport's group-selection match.
 */

import type { OccurrenceFamily, OccurrenceInfo } from "./assemblyMeta";

export interface AssemblyObject {
  id: string;
  name?: string;
}

export interface TreeNode {
  /** Full path id (stable key); also the group prefix for non-leaves. */
  id: string;
  /** Leaf segment for display (last "/"-segment of the id). */
  label: string;
  /** True when this path id is a real object, not just an intermediate group. */
  isLeaf: boolean;
  children: TreeNode[];
  /** Present when this node is an instanced part or sub-assembly (one definition
   *  placed N>1 times). The badge + frame list read from here; the node stands in
   *  for all placements, whose real object ids are in {@link TreeNode.occLeafIds}. */
  occurrences?: OccurrenceInfo[];
  /** Every real object id this node represents, across all its placements. Set
   *  on an occurrence family so visibility/material/selection span all copies;
   *  absent on ordinary nodes (use {@link descendantIds}). */
  occLeafIds?: string[];
  /** True on an instanced SUB-assembly family: its `children` are one group per
   *  placement (each carrying that placement's real internals), instead of the
   *  flat frame list a part family shows. */
  occAssembly?: boolean;
  /** On a per-placement wrapper group (a child of an occAssembly family), the
   *  placement's frame/mirror/label, for the annotation on its row. */
  occInfo?: OccurrenceInfo;
}

/** Last "/"-segment of a path id, used as the display label. */
export function leafLabel(id: string): string {
  const i = id.lastIndexOf("/");
  return i === -1 ? id : id.slice(i + 1);
}

/**
 * Build a nested tree from flat objects whose ids are slash-separated paths.
 * A node is a leaf iff it corresponds to an actual object id; intermediate path
 * segments become group nodes. Order follows first-seen object order.
 *
 * Pass `families` (from `deriveOccurrenceFamilies`) to fold an instanced part's
 * N placements into a single node: the primary placement's node absorbs the
 * others, gains an `occurrences` list (the badge + frame list read from it), and
 * records every underlying object id in `occLeafIds` so visibility, material,
 * and selection still act on all copies.
 */
export function buildAssemblyTree(
  objects: AssemblyObject[],
  families?: Map<string, OccurrenceFamily>,
): TreeNode[] {
  const roots: TreeNode[] = [];
  const byPath = new Map<string, TreeNode>();
  for (const obj of objects) {
    const segs = obj.id.split("/");
    let prefix = "";
    let siblings = roots;
    for (let i = 0; i < segs.length; i++) {
      prefix = prefix ? `${prefix}/${segs[i]}` : segs[i];
      let node = byPath.get(prefix);
      if (!node) {
        node = { id: prefix, label: segs[i], isLeaf: false, children: [] };
        byPath.set(prefix, node);
        siblings.push(node);
      }
      siblings = node.children;
      if (i === segs.length - 1) node.isLeaf = true; // this prefix is a real object
    }
  }
  return families && families.size > 0 ? mergeOccurrenceFamilies(roots, families) : roots;
}

/** Real-object ids in a node's subtree (the node itself if it is a leaf). */
function collectLeafIds(node: TreeNode): string[] {
  const out: string[] = [];
  const walk = (n: TreeNode) => {
    if (n.isLeaf) out.push(n.id);
    n.children.forEach(walk);
  };
  walk(node);
  return out;
}

/**
 * Fold occurrence families in a sibling list: a family's primary node becomes
 * the single instanced row (carrying `occurrences` + `occLeafIds`), the other
 * placements are removed (their geometry rolls into `occLeafIds`). Recurses into
 * every surviving node's children.
 */
function mergeOccurrenceFamilies(
  nodes: TreeNode[],
  families: Map<string, OccurrenceFamily>,
): TreeNode[] {
  // Reverse map: any member id -> its family (so non-primary members are dropped).
  const memberToFamily = new Map<string, OccurrenceFamily>();
  for (const fam of families.values()) {
    for (const id of fam.memberIds) memberToFamily.set(id, fam);
  }

  const out: TreeNode[] = [];
  for (const node of nodes) {
    const fam = memberToFamily.get(node.id);
    if (fam && node.id !== fam.primaryId) continue; // non-primary placement: absorbed

    if (fam && node.id === fam.primaryId) {
      const memberNodes = fam.memberIds.map((mid) => nodes.find((n) => n.id === mid) ?? null);
      // Union every present placement's leaf ids so the row acts on all copies.
      const occLeafIds = memberNodes.flatMap((mn) => (mn ? collectLeafIds(mn) : []));
      // A part family collapses to one badged row (its frame list stands in for
      // geometry). A sub-assembly family keeps one group PER placement, each with
      // that placement's real internals (recursively folding any inner families),
      // so an instanced sub-assembly is fully explorable, not just badged.
      const children: TreeNode[] = fam.isAssembly
        ? memberNodes
            .map((mn, i): TreeNode | null =>
              mn
                ? {
                    id: fam.memberIds[i],
                    label: fam.occurrences[i].label,
                    isLeaf: false,
                    children: mergeOccurrenceFamilies(mn.children, families),
                    occInfo: fam.occurrences[i],
                  }
                : null,
            )
            .filter((n): n is TreeNode => n !== null)
        : [];
      out.push({
        id: node.id,
        label: fam.displayBase,
        isLeaf: false,
        children,
        occurrences: fam.occurrences,
        occLeafIds,
        occAssembly: fam.isAssembly,
      });
      continue;
    }

    out.push({ ...node, children: mergeOccurrenceFamilies(node.children, families) });
  }
  return out;
}

/** Find a node by id anywhere in the tree (depth-first), or null. */
function findNode(nodes: TreeNode[], id: string): TreeNode | null {
  for (const n of nodes) {
    if (n.id === id) return n;
    const hit = findNode(n.children, id);
    if (hit) return hit;
  }
  return null;
}

/**
 * All real-object ids at or under `id` (the id itself if it is a leaf object).
 * Returns [] for an unknown id.
 */
export function descendantIds(tree: TreeNode[], id: string): string[] {
  const start = findNode(tree, id);
  if (!start) return [];
  // An occurrence family stands in for every placement's geometry; its real
  // object ids live in occLeafIds (its `children` are empty by design).
  if (start.occLeafIds) return start.occLeafIds;
  const out: string[] = [];
  const walk = (n: TreeNode) => {
    if (n.isLeaf) out.push(n.id);
    n.children.forEach(walk);
  };
  walk(start);
  return out;
}

/**
 * Does object id `objId` belong to the selection `base`? True for the exact id
 * and any path descendant (`base/...`), plus any occurrence sibling of `base`.
 *
 * Occurrence matching is resolved two ways, in order:
 *   1. EXACT (preferred): `occurrenceOf` is the engine-supplied id of this body's
 *      first-placement counterpart, so this body is an occurrence sibling of
 *      `base` iff that counterpart is `base` or lives under it.
 *   2. HEURISTIC (fallback): only for payloads from a pre-field engine
 *      (`fieldAware === false`). The engine slugs an occurrence's `@N` to `_N`,
 *      so `wheel_2`, `wheel_10` read as siblings of `wheel`. This is what wrongly
 *      co-selects a real part legitimately named `wheel_2`; a field-aware payload
 *      skips it entirely, so absence of `occurrenceOf` there means "not an
 *      occurrence". The `/`-or-digit guards stop `hinge` matching `hingeplate`.
 */
export function idMatchesBase(
  objId: string,
  base: string,
  occurrenceOf?: string | null,
  fieldAware = false,
): boolean {
  if (objId === base || objId.startsWith(base + "/")) return true;
  if (occurrenceOf != null) {
    return occurrenceOf === base || occurrenceOf.startsWith(base + "/");
  }
  if (fieldAware) return false; // field-aware engine, no field => not an occurrence
  if (objId.startsWith(base + "_")) {
    const rest = objId.slice(base.length + 1);
    return /^\d+(\/|$)/.test(rest); // "_2", "_2/pin", "_10" -> occurrence sibling
  }
  return false;
}

/**
 * The object ids that a selection of `target` should resolve to over a FLAT id
 * list: the exact id, any path descendant, and any occurrence sibling (see
 * {@link idMatchesBase}). Uses the legacy `_N` heuristic since a bare id list
 * carries no occurrence field; the object-list path (subtreeIndicesForId) is the
 * exact one.
 */
export function subtreeIdsForId(ids: readonly string[], target: string): string[] {
  return ids.filter((id) => idMatchesBase(id, target));
}
