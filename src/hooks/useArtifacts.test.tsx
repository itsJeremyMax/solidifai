// @vitest-environment jsdom
// DOM test (renderHook needs a DOM): useArtifacts load + recovery behavior.
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";

import { useArtifacts, clearArtifactCache } from "./useArtifacts";

// Mock the ipc boundary. parseModelInfo (from ../lib/artifacts) is NOT mocked, so
// readModelJson must return a real, valid manifest string for the parse to land a
// model. onModelUpdated returns an unlisten fn so the effect cleanup is a no-op.
vi.mock("../lib/ipc/workspace", () => ({
  readModelJson: vi.fn(),
  readModelGlb: vi.fn(),
}));
vi.mock("../lib/ipc/status", () => ({
  onModelUpdated: vi.fn(),
}));

import { readModelJson, readModelGlb } from "../lib/ipc/workspace";
import { onModelUpdated } from "../lib/ipc/status";

const readModelJsonMock = vi.mocked(readModelJson);
const readModelGlbMock = vi.mocked(readModelGlb);
const onModelUpdatedMock = vi.mocked(onModelUpdated);

// Minimal manifest that satisfies parseModelInfo's strict validation, parameterized
// by buildId so we can simulate distinct builds.
function manifest(buildId: number): string {
  return JSON.stringify({
    schema: 2,
    buildId,
    units: "mm",
    build: { ok: true, durationMs: 1, warnings: [] },
    objects: [],
    bbox: { size: [1, 1, 1], min: [0, 0, 0], max: [1, 1, 1] },
    volume: 1,
    centerOfMass: [0, 0, 0],
    mass: { value: 1, material: "aluminum", density: 2.7 },
    valid: true,
    manifold: true,
    params: { schema: {}, values: {} },
  });
}

describe("useArtifacts", () => {
  beforeEach(() => {
    // onModelUpdated resolves to a no-op unlisten so the event path stays inert
    // and tests drive refresh() directly.
    onModelUpdatedMock.mockResolvedValue(() => {});
  });

  afterEach(() => {
    vi.clearAllMocks();
    // Clear the module-level artifact cache between tests so each test starts
    // from a known empty state regardless of what the previous test cached.
    clearArtifactCache("/ws/a");
  });

  it("populates the model + glb on the initial load", async () => {
    readModelJsonMock.mockResolvedValue(manifest(1));
    readModelGlbMock.mockResolvedValue(new Uint8Array([1, 2, 3]));

    const { result } = renderHook(() => useArtifacts("/ws/a"));

    await waitFor(() => expect(result.current.model?.buildId).toBe(1));
    expect(result.current.buildId).toBe(1);
    expect(result.current.glbBytes).toEqual(new Uint8Array([1, 2, 3]));
  });

  it("applies the manifest even when the GLB read fails (json landed first)", async () => {
    // GLB not on disk yet: the manifest still applies, glb stays null. This is the
    // "out of order / partial write" recovery the hook is built to tolerate.
    readModelJsonMock.mockResolvedValue(manifest(2));
    readModelGlbMock.mockRejectedValue(new Error("no glb yet"));

    const { result } = renderHook(() => useArtifacts("/ws/a"));

    await waitFor(() => expect(result.current.model?.buildId).toBe(2));
    expect(result.current.glbBytes).toBeNull();
    expect(result.current.buildId).toBe(-1); // never advanced past the GLB failure
  });

  it("recovers on a refresh after an initial error", async () => {
    // First load: json itself throws -> model stays null (clean empty state).
    readModelJsonMock.mockRejectedValueOnce(new Error("engine not ready"));
    readModelGlbMock.mockResolvedValue(new Uint8Array([9]));

    const { result } = renderHook(() => useArtifacts("/ws/a"));

    await waitFor(() => expect(readModelJsonMock).toHaveBeenCalled());
    expect(result.current.model).toBeNull();

    // Engine comes up; an explicit refresh now succeeds and populates state.
    readModelJsonMock.mockResolvedValue(manifest(3));
    await act(async () => {
      await result.current.refresh();
    });

    expect(result.current.model?.buildId).toBe(3);
    expect(result.current.buildId).toBe(3);
    expect(result.current.glbBytes).toEqual(new Uint8Array([9]));
  });

  // Latest-wins note: a fully deterministic "overlapping refresh, latest wins"
  // race is impractical to force here AND is not actually guaranteed by the hook.
  // The hook only guards the GLB fetch against the EXACT already-loaded buildId
  // (loadedBuildRef equality), and setModel runs unconditionally per refresh, so a
  // late-resolving stale json can still overwrite a newer one. We therefore assert
  // the deduping that IS guaranteed: re-reading the SAME build skips the redundant
  // GLB fetch (no stale re-fetch / churn), rather than asserting cross-refresh
  // ordering the implementation does not promise.
  it("skips the redundant GLB fetch when the build is unchanged", async () => {
    readModelJsonMock.mockResolvedValue(manifest(5));
    readModelGlbMock.mockResolvedValue(new Uint8Array([7]));

    const { result } = renderHook(() => useArtifacts("/ws/a"));

    await waitFor(() => expect(result.current.buildId).toBe(5));
    expect(readModelGlbMock).toHaveBeenCalledTimes(1);

    // Same buildId again: manifest is re-read, but the GLB fetch is deduped.
    await act(async () => {
      await result.current.refresh();
    });

    expect(readModelGlbMock).toHaveBeenCalledTimes(1);
    expect(readModelJsonMock.mock.calls.length).toBeGreaterThan(1);
  });
});
