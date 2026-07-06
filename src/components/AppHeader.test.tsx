// @vitest-environment jsdom
import { describe, it, expect, afterEach, vi } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { HeaderSlotProvider, useHeaderSlot } from "../state/headerSlot";
import { WorkspaceSessionsProvider } from "../state/workspaceSessions";

// The header hosts the global UpdateIndicator, which needs the Tauri-backed
// UpdaterProvider; stub the hook so these layout tests stay provider-free.
vi.mock("../state/updater", () => ({
  useUpdater: () => ({
    status: "idle",
    version: null,
    progress: null,
    error: null,
    startDownload: () => {},
    restart: () => {},
    checkNow: async () => ({ available: false, version: null, error: null }),
  }),
}));

import AppHeader from "./AppHeader";

afterEach(cleanup);

function PublishAction() {
  useHeaderSlot({ actions: <button>my-action</button> });
  return null;
}

describe("AppHeader", () => {
  it("renders the persistent brand linking home", () => {
    render(
      <MemoryRouter>
        <HeaderSlotProvider>
          <WorkspaceSessionsProvider>
            <AppHeader />
          </WorkspaceSessionsProvider>
        </HeaderSlotProvider>
      </MemoryRouter>,
    );
    const brand = screen.getByText("solidifai").closest("a");
    expect(brand?.getAttribute("href")).toBe("/");
  });

  it("renders a page's published actions in the slot", async () => {
    render(
      <MemoryRouter>
        <HeaderSlotProvider>
          <WorkspaceSessionsProvider>
            <AppHeader />
            <PublishAction />
          </WorkspaceSessionsProvider>
        </HeaderSlotProvider>
      </MemoryRouter>,
    );
    expect(await screen.findByText("my-action")).toBeTruthy();
  });
});
