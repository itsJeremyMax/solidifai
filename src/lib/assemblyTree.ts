/**
 * Pure assembly-tree helpers. Phase 2A renders each leaf object with a stable
 * slash-separated path id (e.g. "hinge/pin"), so the assembly hierarchy is
 * fully derivable client-side by splitting ids on "/". No engine call needed.
 *
 * No React here: these are unit-tested in assemblyTree.test.ts and reused by
 * the AssemblyTree component and the viewport's group-selection match.
 */

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
 */
export function buildAssemblyTree(objects: AssemblyObject[]): TreeNode[] {
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
  return roots;
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
  const out: string[] = [];
  const walk = (n: TreeNode) => {
    if (n.isLeaf) out.push(n.id);
    n.children.forEach(walk);
  };
  walk(start);
  return out;
}

/**
 * The object ids that a selection of `target` should resolve to over a FLAT id
 * list: the exact id, plus any descendant whose path id starts with `target/`.
 * This is the viewport's group-selection match (mirrors descendantIds without
 * building a tree). The "/" guard stops "hinge" matching "hingeplate".
 */
export function subtreeIdsForId(ids: readonly string[], target: string): string[] {
  return ids.filter((id) => id === target || id.startsWith(target + "/"));
}
