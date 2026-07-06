// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ArchiveToast } from "./ArchiveToast";

// Click tests use real timers — userEvent does not mix with fake timers.
describe("ArchiveToast", () => {
  afterEach(cleanup);

  it("shows the name and fires onUndo", async () => {
    const onUndo = vi.fn();
    render(<ArchiveToast name="fidget-bracket" onUndo={onUndo} onDismiss={vi.fn()} />);
    expect(screen.getByText(/fidget-bracket/)).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: /undo/i }));
    expect(onUndo).toHaveBeenCalled();
  });
  it("dismiss button fires onDismiss", async () => {
    const onDismiss = vi.fn();
    render(<ArchiveToast name="x" onUndo={vi.fn()} onDismiss={onDismiss} />);
    await userEvent.click(screen.getByRole("button", { name: /dismiss/i }));
    expect(onDismiss).toHaveBeenCalled();
  });
});

describe("ArchiveToast auto-dismiss", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => {
    vi.runOnlyPendingTimers();
    vi.useRealTimers();
    cleanup();
  });

  it("calls onDismiss after the timeout", () => {
    const onDismiss = vi.fn();
    render(<ArchiveToast name="x" onUndo={vi.fn()} onDismiss={onDismiss} />);
    expect(onDismiss).not.toHaveBeenCalled();
    vi.advanceTimersByTime(6000);
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it("a re-render with a new onDismiss reference does NOT reset the timer", () => {
    const onDismiss = vi.fn();
    const { rerender } = render(<ArchiveToast name="x" onUndo={vi.fn()} onDismiss={onDismiss} />);
    vi.advanceTimersByTime(3000);
    rerender(<ArchiveToast name="x" onUndo={vi.fn()} onDismiss={() => onDismiss()} />); // new ref, same name
    vi.advanceTimersByTime(3000); // total 6000 since first mount
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });
});
