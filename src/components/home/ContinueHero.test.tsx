// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ContinueHero } from "./ContinueHero";
import type { Workspace } from "../../lib/workspaces";

afterEach(cleanup);

const ws: Workspace = {
  name: "fidget-bracket",
  path: "/a",
  createdAt: 1,
  lastOpenedAt: 2,
  archivedAt: null,
  description: null,
  tags: [],
  proposedName: null,
};

describe("ContinueHero", () => {
  it("shows the name and fires onContinue", async () => {
    const onContinue = vi.fn();
    render(
      <ContinueHero
        workspace={ws}
        thumbSrc={null}
        onContinue={onContinue}
        onReveal={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByText("fidget-bracket")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(onContinue).toHaveBeenCalledWith(ws);
  });

  it("fires onContinue from the thumbnail too", async () => {
    const onContinue = vi.fn();
    render(
      <ContinueHero
        workspace={ws}
        thumbSrc={null}
        onContinue={onContinue}
        onReveal={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /continue fidget-bracket/i }));
    expect(onContinue).toHaveBeenCalledWith(ws);
  });

  it("fires onReveal from the secondary action", async () => {
    const onReveal = vi.fn();
    render(
      <ContinueHero
        workspace={ws}
        thumbSrc={null}
        onContinue={vi.fn()}
        onReveal={onReveal}
        onClose={vi.fn()}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /reveal in finder/i }));
    expect(onReveal).toHaveBeenCalledWith(ws);
  });

  it("fires onClose from the dismiss button", async () => {
    const onClose = vi.fn();
    render(
      <ContinueHero
        workspace={ws}
        thumbSrc={null}
        onContinue={vi.fn()}
        onReveal={vi.fn()}
        onClose={onClose}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /dismiss/i }));
    expect(onClose).toHaveBeenCalled();
  });
});
