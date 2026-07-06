// @vitest-environment jsdom
import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { HeaderSlotProvider, useHeaderSlot } from "../state/headerSlot";
import { WorkspaceSessionsProvider } from "../state/workspaceSessions";
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
