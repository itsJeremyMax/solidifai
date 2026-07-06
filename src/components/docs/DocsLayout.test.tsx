// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { HeaderSlotProvider } from "../../state/headerSlot";

vi.mock("../../lib/docs", async () => {
  const real = await vi.importActual<typeof import("../../lib/docs")>("../../lib/docs");
  const docs = [
    real.parseDoc("---\ntitle: Getting started\ngroup: Guide\norder: 1\n---\nx", "getting-started.md"),
    real.parseDoc("---\ntitle: Materials\ngroup: Features\norder: 1\n---\nx", "materials.md"),
  ];
  const reg = real.buildRegistry(docs);
  return {
    ...real,
    DOC_REGISTRY: reg,
    DOC_PAGES: reg.ordered,
    DOC_SLUGS: reg.ordered.map((d) => d.slug),
    DOC_SEARCH: real.buildSearchIndex(docs),
  };
});

import DocsLayout from "./DocsLayout";

afterEach(cleanup);

function mount(initial: string) {
  const r = createMemoryRouter(
    [
      {
        path: "/docs",
        element: <DocsLayout />,
        children: [{ path: ":slug", element: <div>doc-outlet</div> }],
      },
    ],
    { initialEntries: [initial] },
  );
  return render(
    <HeaderSlotProvider>
      <RouterProvider router={r} />
    </HeaderSlotProvider>,
  );
}

describe("DocsLayout", () => {
  it("renders grouped nav from the registry and the outlet", async () => {
    mount("/docs/getting-started");
    expect(await screen.findByText("doc-outlet")).toBeTruthy();
    expect(screen.getByText("Guide")).toBeTruthy();
    expect(screen.getByText("Features")).toBeTruthy();
    expect(screen.getByText("Getting started")).toBeTruthy();
    expect(screen.getByText("Materials")).toBeTruthy();
  });
});
