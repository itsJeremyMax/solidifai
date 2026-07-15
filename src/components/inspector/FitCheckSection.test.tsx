// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const toleranceStack = vi.hoisted(() => vi.fn());
vi.mock("../../lib/ipc/engine", () => ({ engineToleranceStack: toleranceStack }));

import FitCheckSection from "./FitCheckSection";

afterEach(() => {
  cleanup();
  toleranceStack.mockReset();
});

const clearance = JSON.stringify({
  ok: true,
  nominal: 10,
  worstCase: { min: 0, max: 0, range: 0 },
  rss: { min: 0, max: 0, range: 0 },
  fit: { type: "clearance", minGap: 0.1, maxGap: 0.2 },
  links: [],
});

describe("FitCheckSection", () => {
  it("clears a previous fit while a new calculation is pending", async () => {
    let resolveNext: (value: string | null) => void = () => {};
    toleranceStack.mockResolvedValueOnce(clearance).mockImplementationOnce(
      () =>
        new Promise<string | null>((resolve) => {
          resolveNext = resolve;
        }),
    );
    render(<FitCheckSection />);
    await screen.findByText("clearance");

    fireEvent.change(screen.getByLabelText("Hole"), { target: { value: "H8" } });

    expect(screen.queryByText("clearance")).toBeNull();
    resolveNext(clearance);
    await screen.findByText("clearance");
  });

  it("shows a failure instead of retaining stale output when the calculation rejects", async () => {
    toleranceStack
      .mockResolvedValueOnce(clearance)
      .mockRejectedValueOnce(new Error("engine unavailable"));
    render(<FitCheckSection />);
    await screen.findByText("clearance");

    fireEvent.change(screen.getByLabelText("Shaft"), { target: { value: "h6" } });

    await waitFor(() =>
      expect(screen.getByText("Couldn't calculate this fit just now.")).toBeTruthy(),
    );
    expect(screen.queryByText("clearance")).toBeNull();
  });
});
