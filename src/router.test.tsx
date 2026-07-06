// @vitest-environment jsdom
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { RouterProvider, createMemoryRouter } from "react-router-dom";

// Neutralize the Tauri-backed shell bits (each has its own suite); this test
// only verifies that a matched route renders inside AppLayout's outlet.
vi.mock("./state/updater", () => ({
  UpdaterProvider: ({ children }: { children: React.ReactNode }) => children,
}));
vi.mock("./components/WhatsNewModal", () => ({ default: () => null }));

import AppLayout from "./components/AppLayout";

describe("app routing", () => {
  it("renders the matched page inside AppLayout's outlet", async () => {
    const r = createMemoryRouter(
      [
        {
          element: <AppLayout />,
          children: [{ path: "/", element: <div>home-stub</div> }],
        },
      ],
      { initialEntries: ["/"] },
    );
    render(<RouterProvider router={r} />);
    expect(await screen.findByText("home-stub")).toBeTruthy();
  });
});
