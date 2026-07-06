// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { WorkspaceSwitcherBar } from "./WorkspaceSwitcher";
import { WorkspaceSessionsProvider } from "../state/workspaceSessions";

// Seed two open tabs (focused on the first) and a matching registry so the
// session provider hydrates them and its prune-on-mount keeps both.
vi.mock("../lib/openTabs", () => ({
  readOpenTabs: () => ({ open: ["/ws/a", "/ws/b"], focused: "/ws/a" }),
  saveOpenTabs: vi.fn(),
}));
vi.mock("../lib/workspaces", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../lib/workspaces")>()), // keep the pure helpers (basename)
  listWorkspaces: async () => [
    { path: "/ws/a", name: "Alpha" },
    { path: "/ws/b", name: "Beta" },
  ],
  closeWorkspaceTab: vi.fn(),
}));
vi.mock("../hooks/useEngineStatus", () => ({
  useWorkspaceStatuses: () => ({ "/ws/a": "ready", "/ws/b": "provisioning" }),
}));

afterEach(cleanup);

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <WorkspaceSessionsProvider>
        <WorkspaceSwitcherBar />
      </WorkspaceSessionsProvider>
    </MemoryRouter>,
  );
}

const EDITOR = `/w/${encodeURIComponent("/ws/a")}`;

describe("WorkspaceSwitcherBar (route-aware form)", () => {
  it("folds to the compact chip on a global page, not the pills", async () => {
    renderAt("/settings");
    // The chip is present (count of open workspaces)...
    expect(await screen.findByLabelText("2 open workspaces")).toBeTruthy();
    // ...and the full pills are not: no segmented pill (aria-pressed), and the
    // workspace names stay tucked inside the closed menu.
    expect(screen.queryByRole("button", { pressed: true })).toBeNull();
    expect(screen.queryByText("Alpha")).toBeNull();
  });

  it("the chip menu lists workspaces most-recently-viewed-first and marks the focused one", async () => {
    renderAt("/factory");
    fireEvent.click(await screen.findByLabelText("2 open workspaces"));
    const alpha = await screen.findByText("Alpha");
    expect(screen.getByText("Beta")).toBeTruthy();
    // Alpha was the last-viewed workspace (the seeded focus), so it sits on top.
    const menu = screen.getByRole("menu");
    const rows = within(menu).getAllByText(/^(Alpha|Beta)$/);
    expect(rows.map((n) => n.textContent)).toEqual(["Alpha", "Beta"]);
    // ...and its row is marked current.
    expect(alpha.closest("button")?.getAttribute("aria-current")).toBe("true");
    expect(screen.getByText("Beta").closest("button")?.getAttribute("aria-current")).toBeNull();
  });

  it("shows the full segmented pills on the editor viewport, not the chip", async () => {
    renderAt(EDITOR);
    // A focused pill (aria-pressed) is rendered; the compact chip is absent.
    expect(await screen.findByRole("button", { pressed: true })).toBeTruthy();
    expect(screen.queryByLabelText(/open workspaces?$/)).toBeNull();
  });
});
