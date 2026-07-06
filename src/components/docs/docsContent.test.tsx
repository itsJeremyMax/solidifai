// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";

// Use the REAL registry (no mock): this exercises the glob, frontmatter parsing,
// and the markdown renderer against the actual authored pages, so a broken table,
// alert, or link in the content fails here rather than in the app.
vi.mock("@tauri-apps/plugin-opener", () => ({ openUrl: vi.fn() }));

import { DOC_PAGES } from "../../lib/docs";
import DocPage from "./DocPage";

afterEach(cleanup);

function mount(slug: string) {
  const r = createMemoryRouter([{ path: "/docs/:slug", element: <DocPage /> }], {
    initialEntries: [`/docs/${slug}`],
  });
  return render(<RouterProvider router={r} />);
}

describe("real doc content", () => {
  it("bundles the starter pages", () => {
    expect(DOC_PAGES.length).toBeGreaterThanOrEqual(6);
  });

  it.each(DOC_PAGES.map((d) => [d.slug, d.title] as const))(
    "renders %s without errors",
    (slug, title) => {
      mount(slug);
      // The page renders without throwing and its title is on the page. The title
      // word can also appear in prose, so allow more than one match.
      expect(screen.getAllByText(title).length).toBeGreaterThanOrEqual(1);
    },
  );
});
