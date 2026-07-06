import { describe, expect, it, vi, beforeEach } from "vitest";

const invoke = vi.fn();
vi.mock("@tauri-apps/api/core", () => ({ invoke: (...a: unknown[]) => invoke(...a) }));

import {
  listWorkspaces,
  archiveWorkspace,
  restoreWorkspace,
  listWorkspaceThumbnails,
  storeWorkspaceThumbnail,
} from "./workspaces";

beforeEach(() => invoke.mockReset());

describe("archivedAt", () => {
  it("defaults archivedAt to null for legacy records", async () => {
    invoke.mockResolvedValueOnce([{ name: "A", path: "/a", createdAt: 1, lastOpenedAt: null }]);
    const list = await listWorkspaces();
    expect(list[0].archivedAt).toBeNull();
  });

  it("parses a numeric archivedAt", async () => {
    invoke.mockResolvedValueOnce([
      { name: "A", path: "/a", createdAt: 1, lastOpenedAt: null, archivedAt: 999 },
    ]);
    const list = await listWorkspaces();
    expect(list[0].archivedAt).toBe(999);
  });

  it("archiveWorkspace returns the updated workspace", async () => {
    invoke.mockResolvedValueOnce({
      name: "A",
      path: "/a",
      createdAt: 1,
      lastOpenedAt: null,
      archivedAt: 5,
    });
    const ws = await archiveWorkspace("/a");
    expect(invoke).toHaveBeenCalledWith("archive_workspace", { path: "/a" });
    expect(ws.archivedAt).toBe(5);
  });

  it("restoreWorkspace re-throws on a bad result", async () => {
    invoke.mockResolvedValueOnce(null);
    await expect(restoreWorkspace("/a")).rejects.toThrow();
  });
});

describe("thumbnails", () => {
  it("listWorkspaceThumbnails filters malformed entries", async () => {
    invoke.mockResolvedValueOnce([
      { path: "/a", dataUrl: "data:image/png;base64,AA", capturedAt: 1, partCount: 2 },
      { path: "/b" }, // malformed → dropped
      "nope", // dropped
    ]);
    const list = await listWorkspaceThumbnails();
    expect(list).toHaveLength(1);
    expect(list[0].path).toBe("/a");
  });

  it("listWorkspaceThumbnails resolves [] on throw", async () => {
    invoke.mockRejectedValueOnce(new Error("x"));
    expect(await listWorkspaceThumbnails()).toEqual([]);
  });

  it("storeWorkspaceThumbnail passes a number array + never throws", async () => {
    invoke.mockResolvedValueOnce(undefined);
    await storeWorkspaceThumbnail("/a", new Uint8Array([1, 2, 3]), 4);
    expect(invoke).toHaveBeenCalledWith("store_workspace_thumbnail", {
      path: "/a",
      png: [1, 2, 3],
      partCount: 4,
    });
    invoke.mockRejectedValueOnce(new Error("x"));
    await expect(storeWorkspaceThumbnail("/a", new Uint8Array([1]), 1)).resolves.toBeUndefined();
  });
});
