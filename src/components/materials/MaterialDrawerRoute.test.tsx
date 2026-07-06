// @vitest-environment jsdom
import { describe, it, expect, afterEach, vi } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { createMemoryRouter, Outlet, RouterProvider } from "react-router-dom";
import type { Material } from "../../lib/materials";
import type { MaterialsOutletContext } from "./materialsContext";

// Stub the heavy editor + preview (shade-ball rendering isn't relevant here).
vi.mock("./MaterialEditor", () => ({
  default: (props: { isNew: boolean; draft: Material }) => (
    <div>editor:{props.isNew ? "new" : props.draft.id}</div>
  ),
  slugify: (s: string) => s,
}));
vi.mock("./MaterialPreviewCard", () => ({ default: () => null }));

import MaterialDrawerRoute from "./MaterialDrawerRoute";

afterEach(cleanup);

const blue: Material = {
  id: "blue",
  label: "Blue",
  base: "pla",
  colorHex: "#00f",
  finish: "matte",
};

function ctx(): MaterialsOutletContext {
  return {
    scope: "global",
    loading: false,
    library: { materials: [blue], default: "blue" },
    globalMaterials: [],
    effectiveDefault: "blue",
    upsert: vi.fn(),
    remove: vi.fn(),
    requestDefault: vi.fn(),
  };
}

function mount(initial: string) {
  const r = createMemoryRouter(
    [
      {
        path: "/materials",
        element: <Outlet context={ctx()} />,
        children: [
          { path: "new", element: <MaterialDrawerRoute /> },
          { path: ":materialId", element: <MaterialDrawerRoute /> },
        ],
      },
    ],
    { initialEntries: [initial] },
  );
  return render(<RouterProvider router={r} />);
}

describe("MaterialDrawerRoute", () => {
  it("opens a new-material draft on the new route", async () => {
    mount("/materials/new");
    expect(await screen.findByText("editor:new")).toBeTruthy();
  });

  it("resolves the material from context on the :materialId route", async () => {
    mount("/materials/blue");
    expect(await screen.findByText("editor:blue")).toBeTruthy();
  });
});
