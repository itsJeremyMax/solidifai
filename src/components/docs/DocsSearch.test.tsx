// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";

vi.mock("../../lib/docs", async () => {
  const real = await vi.importActual<typeof import("../../lib/docs")>("../../lib/docs");
  const docs = [
    real.parseDoc(
      "---\ntitle: Materials\ngroup: Features\n---\nAbout materials and finishes.",
      "materials.md",
    ),
    real.parseDoc("---\ntitle: Getting started\ngroup: Guide\n---\nStart here.", "getting-started.md"),
  ];
  return { ...real, DOC_SEARCH: real.buildSearchIndex(docs) };
});

import { DocsSearchProvider, DocsSearchField } from "./DocsSearch";

afterEach(cleanup);

function mount() {
  const r = createMemoryRouter(
    [
      {
        path: "/docs",
        element: (
          <DocsSearchProvider>
            <DocsSearchField />
          </DocsSearchProvider>
        ),
      },
      { path: "/docs/:slug", element: <div>page</div> },
    ],
    { initialEntries: ["/docs"] },
  );
  return render(<RouterProvider router={r} />);
}

describe("DocsSearch", () => {
  it("opens from the field, filters, and navigates on Enter", async () => {
    mount();
    fireEvent.click(screen.getByRole("button", { name: /search the docs/i }));
    const input = await screen.findByPlaceholderText(/search the docs/i);
    fireEvent.change(input, { target: { value: "material" } });
    expect(screen.getByText("Materials")).toBeTruthy();
    expect(screen.queryByText("Getting started")).toBeNull();
    fireEvent.keyDown(input, { key: "Enter" });
    expect(await screen.findByText("page")).toBeTruthy();
  });

  it("opens with Cmd/Ctrl+K", async () => {
    mount();
    fireEvent.keyDown(window, { key: "k", metaKey: true });
    expect(await screen.findByPlaceholderText(/search the docs/i)).toBeTruthy();
  });
});
