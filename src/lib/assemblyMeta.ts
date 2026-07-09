/**
 * Assembly metadata from the engine's `get_assembly_tree` (protocol 11).
 *
 * The 3D tree the Inspector renders is derived from `model.json`'s flat object
 * list (slash-path ids). That geometry snapshot stays the source of truth for
 * ids, selection, and visibility. What it CANNOT carry is the assembly's
 * declared intent: how many times a part is placed (occurrences), at which
 * frames, whether an occurrence is mirrored, and the skeleton's joints. Those
 * live only in `get_assembly_tree`, which this module fetches and shapes into a
 * form the tree panel can join against the geometry.
 *
 * The join is by path id. An occurrence body lands in `model.json` under a
 * slugged path prefix (`wheel`, `wheel_2`, `wheel_3` — the engine slugs `@` to
 * `_` in `render._node_ids`), while the declared child id here is the clean
 * manifest id (`wheel`). So we slug the child id + its occurrence prefixes the
 * same way to recover the tree-node ids, and keep the clean form for display
 * (`wheel@2`, not `wheel_2`).
 *
 * Everything here is defensive: a single-model workspace, an older engine, or a
 * malformed reply all degrade to `null` (no metadata) rather than throwing into
 * the Inspector.
 */

export type Mirror = "xy" | "yz" | "zx";

/** One placement of a part: the frame it attaches to (null = node origin) and
 *  an optional mirror plane. */
export interface Occurrence {
  frame: string | null;
  mirror: Mirror | null;
}

export type JointKind = "rigid" | "revolute" | "slider" | "cylindrical" | "planar" | "ball";

/** A declared joint on a skeleton: intent + limits, not a solved pose. */
export interface Joint {
  name: string;
  /** Known kinds are listed in {@link JointKind}; unknown strings pass through
   *  so a newer engine never blanks the row. */
  kind: JointKind | string;
  frame: string | null;
  axis: [number, number, number] | null;
  limits: [number, number] | null;
  between: string[] | null;
}

export interface AssemblySkeleton {
  scalars: string[];
  frames: string[];
  shapes: string[];
  joints: Joint[];
}

export interface AssemblyChild {
  id: string;
  kind: string;
  attach: string | null;
  inputs: string[];
  shapeInputs: string[];
  occurrences: Occurrence[];
  /** Present only for `kind === "assembly"`. */
  skeleton: AssemblySkeleton | null;
  children: AssemblyChild[];
}

export interface AssemblyMeta {
  skeleton: AssemblySkeleton | null;
  children: AssemblyChild[];
}

/* ─────────────────────────── slug + prefixes ──────────────────────────── */

/** Mirror of the engine's `render._slug`: non-alphanumerics collapse to `_`,
 *  trimmed, lowercased. `wheel@2` -> `wheel_2`, `My-Part` -> `my_part`. */
export function slug(name: string): string {
  return name
    .replace(/[^a-zA-Z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .toLowerCase();
}

/** Slug each `/`-segment independently, preserving separators (matches the
 *  engine's per-segment slugging of composed path ids). */
export function slugPath(path: string): string {
  return path.split("/").map(slug).join("/");
}

/** Display prefixes for a child's occurrences, in placement order: the first
 *  keeps the bare id, the rest gain `@2`, `@3` ... (mirrors
 *  `compose.occurrence_prefixes`). These are the DISPLAY forms. */
export function occurrencePrefixes(childId: string, count: number): string[] {
  const n = Math.max(1, count);
  return Array.from({ length: n }, (_, i) => (i === 0 ? childId : `${childId}@${i + 1}`));
}

/* ──────────────────────────────── parse ───────────────────────────────── */

function asStringArray(v: unknown): string[] {
  return Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : [];
}

function parseMirror(v: unknown): Mirror | null {
  return v === "xy" || v === "yz" || v === "zx" ? v : null;
}

function parseOccurrences(v: unknown): Occurrence[] {
  if (!Array.isArray(v)) return [];
  return v.map((o) => {
    const rec = (o ?? {}) as Record<string, unknown>;
    return {
      frame: typeof rec.frame === "string" ? rec.frame : null,
      mirror: parseMirror(rec.mirror),
    };
  });
}

function parseAxis(v: unknown): [number, number, number] | null {
  if (Array.isArray(v) && v.length === 3 && v.every((n) => typeof n === "number")) {
    return [v[0], v[1], v[2]] as [number, number, number];
  }
  return null;
}

function parseLimits(v: unknown): [number, number] | null {
  if (Array.isArray(v) && v.length === 2 && v.every((n) => typeof n === "number")) {
    return [v[0], v[1]] as [number, number];
  }
  return null;
}

function parseJoints(v: unknown): Joint[] {
  if (!Array.isArray(v)) return [];
  const out: Joint[] = [];
  for (const j of v) {
    const rec = (j ?? {}) as Record<string, unknown>;
    if (typeof rec.name !== "string" || typeof rec.kind !== "string") continue;
    out.push({
      name: rec.name,
      kind: rec.kind,
      frame: typeof rec.frame === "string" ? rec.frame : null,
      axis: parseAxis(rec.axis),
      limits: parseLimits(rec.limits),
      between: Array.isArray(rec.between) ? asStringArray(rec.between) : null,
    });
  }
  return out;
}

function parseSkeleton(v: unknown): AssemblySkeleton | null {
  if (!v || typeof v !== "object") return null;
  const rec = v as Record<string, unknown>;
  return {
    scalars: asStringArray(rec.scalars),
    frames: asStringArray(rec.frames),
    shapes: asStringArray(rec.shapes),
    joints: parseJoints(rec.joints),
  };
}

function parseChild(v: unknown): AssemblyChild | null {
  if (!v || typeof v !== "object") return null;
  const rec = v as Record<string, unknown>;
  if (typeof rec.id !== "string") return null;
  return {
    id: rec.id,
    kind: typeof rec.kind === "string" ? rec.kind : "part",
    attach: typeof rec.attach === "string" ? rec.attach : null,
    inputs: asStringArray(rec.inputs),
    shapeInputs: asStringArray(rec.shape_inputs),
    occurrences: parseOccurrences(rec.occurrences),
    skeleton: parseSkeleton(rec.skeleton),
    children: Array.isArray(rec.children)
      ? rec.children.map(parseChild).filter((c): c is AssemblyChild => c !== null)
      : [],
  };
}

/**
 * Parse a raw `get_assembly_tree` response into {@link AssemblyMeta}, or `null`
 * when there is no usable metadata (not an assembly, older engine, `ok:false`,
 * or malformed). Never throws.
 */
export function parseAssemblyTree(raw: string | null): AssemblyMeta | null {
  if (!raw) return null;
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!data || typeof data !== "object") return null;
  const rec = data as Record<string, unknown>;
  if (rec.ok !== true) return null; // single-model workspace or engine-reported error
  const tree = rec.tree;
  if (!tree || typeof tree !== "object") return null;
  const treeRec = tree as Record<string, unknown>;
  return {
    skeleton: parseSkeleton(treeRec.skeleton),
    children: Array.isArray(treeRec.children)
      ? treeRec.children.map(parseChild).filter((c): c is AssemblyChild => c !== null)
      : [],
  };
}

/* ───────────────────────── derived, tree-facing ───────────────────────── */

/** One occurrence's placement, with a display label ("wheel@2"). */
export interface OccurrenceInfo {
  frame: string | null;
  mirror: Mirror | null;
  label: string;
}

/** An instanced part: one definition placed N>1 times. Keyed for the tree by
 *  the slugged path id of its FIRST placement (the node kept after merging). */
export interface OccurrenceFamily {
  /** Slugged path id of the primary placement, e.g. "wheel" or "rig/wheel". */
  primaryId: string;
  /** Clean display name, e.g. "wheel". */
  displayBase: string;
  /** Slugged path ids of every placement, in order: ["wheel","wheel_2",...]. */
  memberIds: string[];
  occurrences: OccurrenceInfo[];
}

/** A joint, path-qualified for display when it lives on a sub-skeleton. */
export interface JointInfo extends Joint {
  displayName: string;
}

/**
 * Occurrence families keyed by their primary slugged path id. Walks the assembly
 * recursively; a child placed more than once yields one family. Nested children
 * are discovered along the PRIMARY placement's path (an instanced sub-assembly
 * still gets its badge; its per-instance internals are not separately expanded).
 */
export function deriveOccurrenceFamilies(meta: AssemblyMeta | null): Map<string, OccurrenceFamily> {
  const out = new Map<string, OccurrenceFamily>();
  if (!meta) return out;

  const walk = (children: AssemblyChild[], rawParent: string): void => {
    for (const child of children) {
      const count = Math.max(1, child.occurrences.length);
      const prefixes = occurrencePrefixes(child.id, count);
      const rawPaths = prefixes.map((p) => (rawParent ? `${rawParent}/${p}` : p));
      const memberIds = rawPaths.map(slugPath);

      if (count > 1) {
        out.set(memberIds[0], {
          primaryId: memberIds[0],
          displayBase: child.id,
          memberIds,
          occurrences: child.occurrences.map((o, i) => ({
            frame: o.frame,
            mirror: o.mirror,
            label: prefixes[i],
          })),
        });
      }

      if (child.kind === "assembly" && child.children.length > 0) {
        // Recurse along the primary placement's path so nested slugged ids line
        // up with the geometry snapshot.
        walk(child.children, rawPaths[0]);
      }
    }
  };

  walk(meta.children, "");
  return out;
}

/**
 * Every declared joint, root first, then any sub-assembly joints with a
 * path-qualified `displayName` ("arm/wrist"). Root joints keep their bare name.
 */
export function deriveJoints(meta: AssemblyMeta | null): JointInfo[] {
  const out: JointInfo[] = [];
  if (!meta) return out;

  const walk = (
    skeleton: AssemblySkeleton | null,
    children: AssemblyChild[],
    rawPrefix: string,
  ): void => {
    for (const j of skeleton?.joints ?? []) {
      out.push({ ...j, displayName: rawPrefix ? `${rawPrefix}/${j.name}` : j.name });
    }
    for (const child of children) {
      if (child.kind === "assembly" && child.skeleton) {
        walk(child.skeleton, child.children, rawPrefix ? `${rawPrefix}/${child.id}` : child.id);
      }
    }
  };

  walk(meta.skeleton, meta.children, "");
  return out;
}
