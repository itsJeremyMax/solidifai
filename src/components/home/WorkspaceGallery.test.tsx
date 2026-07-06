// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { WorkspaceGallery } from "./WorkspaceGallery";
import type { Workspace } from "../../lib/workspaces";

afterEach(cleanup);

const mk = (name: string): Workspace => ({
  name,
  path: "/" + name,
  createdAt: 1,
  lastOpenedAt: 2,
  archivedAt: null,
  description: null,
  tags: [],
  proposedName: null,
});
const base = {
  thumbs: {},
  busyKey: null,
  onOpen: vi.fn(),
  onEditDetails: vi.fn(),
  onArchive: vi.fn(),
  onRestore: vi.fn(),
  onDelete: vi.fn(),
  onAcceptName: vi.fn(),
  onDismissName: vi.fn(),
};

describe("WorkspaceGallery", () => {
  it("renders a card per workspace and opens the right one", async () => {
    const onOpen = vi.fn();
    render(
      <WorkspaceGallery
        {...base}
        view="grid"
        workspaces={[mk("alpha"), mk("beta")]}
        onOpen={onOpen}
      />,
    );
    expect(screen.getByText("alpha")).toBeTruthy();
    expect(screen.getByText("beta")).toBeTruthy();
    await userEvent.click(screen.getByText("beta"));
    expect(onOpen).toHaveBeenCalledTimes(1);
    expect(onOpen.mock.calls[0][0].name).toBe("beta");
  });

  it("list mode renders rows too", () => {
    render(<WorkspaceGallery {...base} view="list" workspaces={[mk("gamma")]} />);
    expect(screen.getByText("gamma")).toBeTruthy();
  });
});
