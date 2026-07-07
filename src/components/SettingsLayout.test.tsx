// @vitest-environment jsdom
import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { HeaderSlotProvider } from "../state/headerSlot";
import SettingsLayout from "./SettingsLayout";
import type { SettingsSection } from "./settings/sections";

afterEach(cleanup);

const SECTIONS: SettingsSection[] = [
  {
    id: "viewport",
    label: "Viewport / Features",
    group: "Editor",
    icon: <i />,
    element: <div>viewport-pane</div>,
  },
  { id: "about", label: "About", group: "App", icon: <i />, element: <div>about-pane</div> },
];

function mount(initial: string, crossLink?: { to: string; label: string }) {
  const r = createMemoryRouter(
    [
      {
        path: "/settings",
        element: <SettingsLayout sections={SECTIONS} title="Settings" crossLink={crossLink} />,
        children: SECTIONS.map((s) => ({ path: s.id, element: s.element })),
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

describe("SettingsLayout", () => {
  it("renders the passed sidebar registry and the active section in the outlet", async () => {
    mount("/settings/viewport");
    expect(await screen.findByText("viewport-pane")).toBeTruthy();
    // Sidebar labels come from the passed section list.
    expect(screen.getByText("Viewport / Features")).toBeTruthy();
    expect(screen.getByText("About")).toBeTruthy();
  });

  it("swaps the outlet when the route changes", async () => {
    mount("/settings/about");
    expect(await screen.findByText("about-pane")).toBeTruthy();
    expect(screen.queryByText("viewport-pane")).toBeNull();
  });

  it("renders a cross-link to the sibling settings page when given one", async () => {
    mount("/settings/viewport", { to: "/settings", label: "App settings" });
    expect(await screen.findByText("App settings")).toBeTruthy();
  });
});
