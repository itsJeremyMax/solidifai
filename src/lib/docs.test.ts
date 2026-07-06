import { describe, it, expect } from "vitest";
import { parseDoc, buildRegistry, buildSearchIndex } from "./docs";

const A = `---
title: Getting started
group: Guide
order: 1
description: Open a workspace and build your first part.
---
Welcome to solidifai.

## Creating a workspace
Hit New workspace and you land in the editor.
`;

const B = `---
title: Materials
group: Features
order: 2
---
Body text about materials.
`;

describe("parseDoc", () => {
  it("reads frontmatter, derives the slug, and keeps the body", () => {
    const doc = parseDoc(A, "getting-started.md");
    expect(doc.slug).toBe("getting-started");
    expect(doc.title).toBe("Getting started");
    expect(doc.group).toBe("Guide");
    expect(doc.order).toBe(1);
    expect(doc.description).toBe("Open a workspace and build your first part.");
    expect(doc.body).toContain("Welcome to solidifai.");
    expect(doc.body).not.toContain("title:");
  });

  it("defaults group to Guide and order to Infinity when absent", () => {
    const doc = parseDoc("---\ntitle: X\n---\nhi", "x.md");
    expect(doc.group).toBe("Guide");
    expect(doc.order).toBe(Number.POSITIVE_INFINITY);
  });

  it("derives the slug from a full glob path", () => {
    const doc = parseDoc("---\ntitle: Y\n---\nbody", "/docs/guide/the-editor.md");
    expect(doc.slug).toBe("the-editor");
  });
});

describe("buildRegistry", () => {
  it("groups by group and sorts by order within a group", () => {
    const reg = buildRegistry([parseDoc(B, "materials.md"), parseDoc(A, "getting-started.md")]);
    expect(reg.groups.map((g) => g.label)).toEqual(["Features", "Guide"]);
    expect(reg.bySlug["materials"].title).toBe("Materials");
    expect(reg.bySlug["getting-started"].order).toBe(1);
    // ordered is the flat nav order (groups in first-seen order, pages by order)
    expect(reg.ordered.map((d) => d.slug)).toEqual(["materials", "getting-started"]);
  });

  it("sorts multiple pages in a group by order", () => {
    const reg = buildRegistry([
      parseDoc("---\ntitle: Second\ngroup: Guide\norder: 2\n---\nx", "second.md"),
      parseDoc("---\ntitle: First\ngroup: Guide\norder: 1\n---\nx", "first.md"),
    ]);
    expect(reg.groups[0].pages.map((p) => p.slug)).toEqual(["first", "second"]);
  });
});

describe("buildSearchIndex", () => {
  it("indexes title, headings, and body text per page", () => {
    const idx = buildSearchIndex([parseDoc(A, "getting-started.md")]);
    const hit = idx.find((e) => e.slug === "getting-started")!;
    expect(hit.title).toBe("Getting started");
    expect(hit.headings).toContain("Creating a workspace");
    expect(hit.text.toLowerCase()).toContain("workspace");
  });

  it("drops code fences from the search text", () => {
    const idx = buildSearchIndex([
      parseDoc("---\ntitle: Z\n---\nReal text.\n\n```\nsecretcode\n```\n", "z.md"),
    ]);
    expect(idx[0].text).toContain("real text");
    expect(idx[0].text).not.toContain("secretcode");
  });
});
