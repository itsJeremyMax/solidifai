// @vitest-environment jsdom
import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { HeaderSlotProvider } from "../state/headerSlot";
import SettingsLayout from "./SettingsLayout";

afterEach(cleanup);

function mount(initial: string) {
  const r = createMemoryRouter(
    [
      {
        path: "/settings",
        element: <SettingsLayout />,
        children: [
          { path: "viewport", element: <div>viewport-pane</div> },
          { path: "about", element: <div>about-pane</div> },
        ],
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
  it("renders the registry-driven sidebar and the active section in the outlet", async () => {
    mount("/settings/viewport");
    expect(await screen.findByText("viewport-pane")).toBeTruthy();
    // Sidebar labels come from the section registry.
    expect(screen.getByText("Viewport / Features")).toBeTruthy();
    expect(screen.getByText("About")).toBeTruthy();
    expect(screen.getByText("Keyboard shortcuts")).toBeTruthy();
  });

  it("swaps the outlet when the route changes", async () => {
    mount("/settings/about");
    expect(await screen.findByText("about-pane")).toBeTruthy();
    expect(screen.queryByText("viewport-pane")).toBeNull();
  });
});
