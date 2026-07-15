// @vitest-environment jsdom
// DOM test (renderHook needs a DOM): useArtifacts load + recovery behavior.
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";

import { useArtifacts, clearArtifactCache } from "./useArtifacts";

// Mock the IPC boundary. parseModelInfo (from ../lib/artifacts) is NOT mocked, so
// snapshots carry real manifest strings. onModelUpdated returns an unlisten fn so
// the event path stays inert unless a test drives it.
vi.mock("../lib/ipc/workspace", () => ({
  readModelSnapshot: vi.fn(),
}));
vi.mock("../lib/ipc/status", () => ({
  onModelUpdated: vi.fn(),
}));

import { readModelSnapshot } from "../lib/ipc/workspace";
import { onModelUpdated } from "../lib/ipc/status";

const readModelSnapshotMock = vi.mocked(readModelSnapshot);
const onModelUpdatedMock = vi.mocked(onModelUpdated);

// Minimal manifest that satisfies parseModelInfo's strict validation, parameterized
// by buildId so we can simulate distinct builds.
function manifest(
  buildId: number,
  publicationId = `pub-${buildId}`,
  { empty = false }: { empty?: boolean } = {},
): string {
  return JSON.stringify({
    schema: 2,
    buildId,
    publicationId,
    units: "mm",
    build: { ok: true, durationMs: 1, warnings: [] },
    objects: empty
      ? []
      : [{ id: "body", name: "Body", kind: "Solid", node: "body", visible: true }],
    bbox: empty ? null : { size: [1, 1, 1], min: [0, 0, 0], max: [1, 1, 1] },
    volume: empty ? 0 : 1,
    centerOfMass: empty ? null : [0, 0, 0],
    mass: { value: 1, material: "aluminum", density: 2.7 },
    valid: true,
    manifold: true,
    params: { schema: {}, values: {} },
  });
}

function snapshot(buildId: number, glb: number[] = [buildId]) {
  return { publicationId: `pub-${buildId}`, manifest: manifest(buildId), glb };
}

function emptySnapshot(buildId: number) {
  return {
    publicationId: `pub-${buildId}`,
    manifest: manifest(buildId, `pub-${buildId}`, { empty: true }),
    glb: [],
  };
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
    readModelSnapshotMock.mockResolvedValue(snapshot(1, [1, 2, 3]));

    const { result } = renderHook(() => useArtifacts("/ws/a"));

    await waitFor(() => expect(result.current.model?.buildId).toBe(1));
    expect(result.current.buildId).toBe(1);
    expect(result.current.glbBytes).toEqual(new Uint8Array([1, 2, 3]));
  });

  it("keeps the existing coherent pair when a snapshot read fails", async () => {
    readModelSnapshotMock.mockRejectedValue(new Error("snapshot unavailable"));

    const { result } = renderHook(() => useArtifacts("/ws/a"));

    await waitFor(() => expect(readModelSnapshotMock).toHaveBeenCalled());
    expect(result.current.model).toBeNull();
    expect(result.current.glbBytes).toBeNull();
    expect(result.current.buildId).toBe(-1);
  });

  it("recovers on a refresh after an initial error", async () => {
    // First load: json itself throws -> model stays null (clean empty state).
    readModelSnapshotMock.mockRejectedValueOnce(new Error("engine not ready"));

    const { result } = renderHook(() => useArtifacts("/ws/a"));

    await waitFor(() => expect(readModelSnapshotMock).toHaveBeenCalled());
    expect(result.current.model).toBeNull();

    // Engine comes up; an explicit refresh now succeeds and populates state.
    readModelSnapshotMock.mockResolvedValue(snapshot(3, [9]));
    await act(async () => {
      await result.current.refresh();
    });

    expect(result.current.model?.buildId).toBe(3);
    expect(result.current.buildId).toBe(3);
    expect(result.current.glbBytes).toEqual(new Uint8Array([9]));
  });

  it("uses publication identity when an engine restart reuses a build id", async () => {
    readModelSnapshotMock.mockResolvedValueOnce(snapshot(5, [7]));

    const { result } = renderHook(() => useArtifacts("/ws/a"));

    await waitFor(() => expect(result.current.buildId).toBe(5));
    expect(result.current.glbBytes).toEqual(new Uint8Array([7]));

    readModelSnapshotMock.mockResolvedValueOnce({
      publicationId: "pub-after-restart",
      manifest: manifest(5, "pub-after-restart"),
      glb: [8],
    });
    await act(async () => {
      await result.current.refresh();
    });

    expect(result.current.glbBytes).toEqual(new Uint8Array([8]));
  });

  it("replaces the final part with an empty publication", async () => {
    readModelSnapshotMock.mockResolvedValueOnce(snapshot(1, [1]));
    const { result } = renderHook(() => useArtifacts("/ws/a"));
    await waitFor(() => expect(result.current.model?.buildId).toBe(1));

    readModelSnapshotMock.mockResolvedValueOnce(emptySnapshot(2));
    await act(async () => {
      await result.current.refresh();
    });

    expect(result.current.model?.objects).toEqual([]);
    expect(result.current.glbBytes).toEqual(new Uint8Array());
    expect(result.current.buildId).toBe(2);
  });

  it("keeps the latest empty publication when an older non-empty refresh resolves", async () => {
    let resolveFirst!: (value: ReturnType<typeof snapshot>) => void;
    const first = new Promise<ReturnType<typeof snapshot>>((resolve) => {
      resolveFirst = resolve;
    });
    readModelSnapshotMock.mockReturnValueOnce(first).mockResolvedValueOnce(emptySnapshot(2));

    const { result } = renderHook(() => useArtifacts("/ws/a"));
    await act(async () => {
      await result.current.refresh();
    });
    await waitFor(() => expect(result.current.model?.objects).toEqual([]));

    await act(async () => {
      resolveFirst(snapshot(1, [1]));
      await first;
    });
    expect(result.current.model?.objects).toEqual([]);
    expect(result.current.glbBytes).toEqual(new Uint8Array());
  });

  it("keeps accepting a legacy publication without a publication id", async () => {
    readModelSnapshotMock.mockResolvedValue({
      publicationId: null,
      manifest: manifest(4, "legacy"),
      glb: [4],
    });

    const { result } = renderHook(() => useArtifacts("/ws/a"));
    await waitFor(() => expect(result.current.model?.buildId).toBe(4));
    expect(result.current.publicationId).toBeNull();
    expect(result.current.glbBytes).toEqual(new Uint8Array([4]));
  });

  it("keeps the latest snapshot when an older refresh resolves afterwards", async () => {
    let resolveFirst!: (value: ReturnType<typeof snapshot>) => void;
    const first = new Promise<ReturnType<typeof snapshot>>((resolve) => {
      resolveFirst = resolve;
    });
    readModelSnapshotMock.mockReturnValueOnce(first).mockResolvedValueOnce(snapshot(2, [2]));

    const { result } = renderHook(() => useArtifacts("/ws/a"));
    await act(async () => {
      await result.current.refresh();
    });
    await waitFor(() => expect(result.current.model?.buildId).toBe(2));

    await act(async () => {
      resolveFirst(snapshot(1, [1]));
      await first;
    });
    expect(result.current.model?.buildId).toBe(2);
    expect(result.current.glbBytes).toEqual(new Uint8Array([2]));
  });
});
