// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { WorkspaceGridCard } from "./WorkspaceGridCard";
import type { Workspace } from "../../lib/workspaces";

afterEach(cleanup);

const ws: Workspace = {
  name: "vesa-mount",
  path: "/Users/me/vesa-mount",
  createdAt: 1,
  lastOpenedAt: 2,
  archivedAt: null,
  description: null,
  tags: [],
  proposedName: null,
};
const noop = () => {};
const base = {
  ws,
  thumbSrc: null,
  busy: false,
  disabled: false,
  onOpen: noop,
  onEditDetails: noop,
  onArchive: noop,
  onRestore: noop,
  onDelete: noop,
  onAcceptName: noop,
  onDismissName: noop,
};

describe("WorkspaceGridCard", () => {
  it("opens on body click", async () => {
    const onOpen = vi.fn();
    render(<WorkspaceGridCard {...base} onOpen={onOpen} />);
    await userEvent.click(screen.getByText("vesa-mount"));
    expect(onOpen).toHaveBeenCalled();
  });
  it("archived card offers Restore not Archive", async () => {
    render(<WorkspaceGridCard {...base} ws={{ ...ws, archivedAt: 5 }} />);
    await userEvent.click(screen.getByRole("button", { name: /workspace actions/i }));
    expect(screen.getByRole("button", { name: /restore/i })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /^archive$/i })).toBeNull();
  });
  it("shows rename suggestion badge and actions when proposedName is set", async () => {
    const onAcceptName = vi.fn();
    const onDismissName = vi.fn();
    render(
      <WorkspaceGridCard
        {...base}
        ws={{ ...ws, proposedName: "vesa-bracket" }}
        onAcceptName={onAcceptName}
        onDismissName={onDismissName}
      />,
    );
    expect(screen.getByText(/rename suggested/i)).toBeTruthy();
    expect(screen.getByText("vesa-bracket")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: /accept/i }));
    expect(onAcceptName).toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: /dismiss/i }));
    expect(onDismissName).toHaveBeenCalled();
  });
  it("does not show rename suggestion on archived cards", () => {
    render(
      <WorkspaceGridCard {...base} ws={{ ...ws, archivedAt: 5, proposedName: "vesa-bracket" }} />,
    );
    expect(screen.queryByText(/rename suggested/i)).toBeNull();
  });
});
