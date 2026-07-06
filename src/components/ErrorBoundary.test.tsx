// @vitest-environment jsdom
// DOM test: ErrorBoundary catches a render throw and recovers via "Try again".
// Opted into jsdom per-file so the global node env (used by the pure-logic tests)
// stays fast.
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";

import ErrorBoundary from "./ErrorBoundary";

// Module-level flag so "Try again" (which remounts the subtree) can succeed: we
// flip it false before clicking, so the remounted child renders cleanly instead
// of throwing again.
let shouldThrow = true;

function Boom() {
  if (shouldThrow) throw new Error("kaboom");
  return <div>recovered child</div>;
}

describe("ErrorBoundary", () => {
  // Suppress the expected uncaught-error chatter from a deliberate render throw:
  // React rethrows in dev (for the error overlay) and jsdom dispatches that to its
  // virtual console. Swallowing the window error event keeps the run output clean
  // without masking real failures (the assertions still drive pass/fail).
  const swallow = (e: Event) => e.preventDefault();

  beforeEach(() => {
    shouldThrow = true;
    // React also logs caught render errors via console.error; silence that too.
    vi.spyOn(console, "error").mockImplementation(() => {});
    window.addEventListener("error", swallow);
  });

  afterEach(() => {
    window.removeEventListener("error", swallow);
    cleanup();
    vi.restoreAllMocks();
  });

  it("renders children normally when nothing throws", () => {
    render(
      <ErrorBoundary>
        <div>healthy child</div>
      </ErrorBoundary>,
    );
    expect(screen.getByText("healthy child")).toBeTruthy();
    expect(screen.queryByText("Something went wrong")).toBeNull();
  });

  it("shows the fallback when a child throws during render", () => {
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    );
    expect(screen.getByText("Something went wrong")).toBeTruthy();
    // The thrown message is surfaced in the fallback's detail block.
    expect(screen.getByText("kaboom")).toBeTruthy();
  });

  it("clears the error and re-renders children after Try again", () => {
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    );
    expect(screen.getByText("Something went wrong")).toBeTruthy();

    // Stop the child from throwing, then reset the boundary; the remounted
    // subtree should now render its happy-path content.
    shouldThrow = false;
    fireEvent.click(screen.getByText("Try again"));

    expect(screen.getByText("recovered child")).toBeTruthy();
    expect(screen.queryByText("Something went wrong")).toBeNull();
  });
});
