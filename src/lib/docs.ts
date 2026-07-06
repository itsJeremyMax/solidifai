/**
 * Docs registry. Markdown files in /docs/guide carry small frontmatter and are
 * bundled at build time. Authoring a page is dropping a file in that folder; the
 * nav, routes, and search all derive from what is on disk. The parse helpers are
 * pure so they can be unit tested without the glob.
 */

export interface Doc {
  slug: string;
  title: string;
  group: string;
  order: number;
  description: string;
  body: string;
}

export interface DocGroup {
  label: string;
  pages: Doc[];
}

export interface DocRegistry {
  ordered: Doc[]; // flat, in nav order
  groups: DocGroup[]; // grouped, first-seen group order, pages sorted by order
  bySlug: Record<string, Doc>;
}

export interface SearchEntry {
  slug: string;
  title: string;
  group: string;
  description: string;
  headings: string[];
  text: string; // lowercased plain-ish body, for matching
}

const FRONTMATTER = /^---\n([\s\S]*?)\n---\n?/;

/** Parse one raw markdown file into a Doc. The slug comes from the filename. */
export function parseDoc(raw: string, filename: string): Doc {
  const slug = filename.replace(/.*\//, "").replace(/\.md$/, "");
  const m = raw.match(FRONTMATTER);
  const meta: Record<string, string> = {};
  let body = raw;
  if (m) {
    body = raw.slice(m[0].length);
    for (const line of m[1].split("\n")) {
      const i = line.indexOf(":");
      if (i === -1) continue;
      const key = line.slice(0, i).trim();
      const val = line.slice(i + 1).trim();
      if (key) meta[key] = val;
    }
  }
  const parsedOrder = meta.order != null ? Number(meta.order) : Number.POSITIVE_INFINITY;
  return {
    slug,
    title: meta.title ?? slug,
    group: meta.group ?? "Guide",
    order: Number.isFinite(parsedOrder) ? parsedOrder : Number.POSITIVE_INFINITY,
    description: meta.description ?? "",
    body: body.trimStart(),
  };
}

/** Build the grouped, ordered registry from parsed docs. */
export function buildRegistry(docs: Doc[]): DocRegistry {
  const order: string[] = [];
  const byGroup = new Map<string, Doc[]>();
  for (const d of docs) {
    if (!byGroup.has(d.group)) {
      byGroup.set(d.group, []);
      order.push(d.group);
    }
    byGroup.get(d.group)!.push(d);
  }
  const groups = order.map((label) => ({
    label,
    pages: byGroup
      .get(label)!
      .slice()
      .sort((a, b) => a.order - b.order),
  }));
  const ordered = groups.flatMap((g) => g.pages);
  const bySlug: Record<string, Doc> = {};
  for (const d of ordered) bySlug[d.slug] = d;
  return { ordered, groups, bySlug };
}

/** Stable id for a heading, used by the on-this-page rail and deep links. */
export function slugifyHeading(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^\w\s-]/g, "")
    .trim()
    .replace(/\s+/g, "-");
}

/** Extract ATX headings (## and ### lines) from a markdown body. */
export function extractHeadings(body: string): string[] {
  const out: string[] = [];
  for (const line of body.split("\n")) {
    const m = line.match(/^#{2,3}\s+(.*)$/);
    if (m) out.push(m[1].trim());
  }
  return out;
}

/** Build a flat search index from parsed docs. */
export function buildSearchIndex(docs: Doc[]): SearchEntry[] {
  return docs.map((d) => ({
    slug: d.slug,
    title: d.title,
    group: d.group,
    description: d.description,
    headings: extractHeadings(d.body),
    text: d.body
      .replace(/```[\s\S]*?```/g, " ") // drop fenced code
      .replace(/[#>*_`-]/g, " ")
      .replace(/\s+/g, " ")
      .trim()
      .toLowerCase(),
  }));
}

/** All docs, bundled at build time. The glob is relative to the project root. */
const RAW = import.meta.glob("/docs/guide/*.md", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

const DOCS: Doc[] = Object.entries(RAW).map(([path, raw]) => parseDoc(raw, path));

export const DOC_REGISTRY: DocRegistry = buildRegistry(DOCS);
export const DOC_SEARCH: SearchEntry[] = buildSearchIndex(DOCS);
export const DOC_PAGES = DOC_REGISTRY.ordered;
export const DOC_SLUGS = DOC_PAGES.map((d) => d.slug);
export const getDoc = (slug: string): Doc | undefined => DOC_REGISTRY.bySlug[slug];
