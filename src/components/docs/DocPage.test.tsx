// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";

vi.mock("@tauri-apps/plugin-opener", () => ({ openUrl: vi.fn() }));
vi.mock("../../lib/docs", async () => {
  const real = await vi.importActual<typeof import("../../lib/docs")>("../../lib/docs");
  const docs = [
    real.parseDoc(
      "---\ntitle: Getting started\ngroup: Guide\norder: 1\n---\nWelcome.\n\n## First steps\nGo.",
      "getting-started.md",
    ),
    real.parseDoc("---\ntitle: Editor\ngroup: Guide\norder: 2\n---\nEditor body.", "editor.md"),
  ];
  const reg = real.buildRegistry(docs);
  return {
    ...real,
    DOC_REGISTRY: reg,
    DOC_PAGES: reg.ordered,
    DOC_SLUGS: reg.ordered.map((d) => d.slug),
    getDoc: (s: string) => reg.bySlug[s],
  };
});

import DocPage from "./DocPage";

afterEach(cleanup);

function mount(initial: string) {
  const r = createMemoryRouter([{ path: "/docs/:slug", element: <DocPage /> }], {
    initialEntries: [initial],
  });
  return render(<RouterProvider router={r} />);
}

describe("DocPage", () => {
  it("renders the matched page title and body", async () => {
    mount("/docs/getting-started");
    expect(await screen.findByText("Getting started")).toBeTruthy();
    expect(screen.getByText("Welcome.")).toBeTruthy();
    // "First steps" appears in the body heading and in the on-this-page rail.
    expect(screen.getAllByText("First steps").length).toBeGreaterThanOrEqual(2);
  });

  it("shows a previous link from registry order", async () => {
    mount("/docs/editor");
    expect(await screen.findByText("Editor body.")).toBeTruthy();
    expect(screen.getByText("Previous")).toBeTruthy();
    expect(screen.getByText("Getting started")).toBeTruthy();
  });

  it("redirects an unknown slug to the first page", async () => {
    mount("/docs/nope");
    expect(await screen.findByText("Welcome.")).toBeTruthy();
  });
});
