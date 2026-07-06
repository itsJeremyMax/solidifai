// @vitest-environment jsdom
import { describe, test, expect, afterEach, beforeEach, vi } from "vitest";
import { render, act, cleanup } from "@testing-library/react";
import { WorkspaceSessionsProvider, useWorkspaceSessions } from "./workspaceSessions";
import { saveOpenTabs } from "../lib/openTabs";
import { clearArtifactCache } from "../hooks/useArtifacts";
import { clearEditorView } from "./editorViewState";

// Mock listWorkspaces to return an empty list (avoids Tauri invoke in tests).
vi.mock("../lib/workspaces", () => ({
  listWorkspaces: vi.fn().mockResolvedValue([]),
}));

// Spy on the per-path cache evictors so we can assert a session teardown clears
// them (the GLB cache lives behind a Tauri-backed module; stub it out wholesale).
vi.mock("../hooks/useArtifacts", () => ({ clearArtifactCache: vi.fn() }));
vi.mock("./editorViewState", () => ({ clearEditorView: vi.fn() }));

// Stub localStorage with a simple in-memory store (in-memory stub).
const store = new Map<string, string>();
beforeEach(() => {
  store.clear();
  vi.clearAllMocks();
  vi.stubGlobal("localStorage", {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => {
      store.set(k, v);
    },
    removeItem: (k: string) => {
      store.delete(k);
    },
    clear: () => store.clear(),
  });
});

afterEach(cleanup);

function Probe({ onReady }: { onReady: (api: ReturnType<typeof useWorkspaceSessions>) => void }) {
  onReady(useWorkspaceSessions());
  return null;
}

describe("WorkspaceSessionsProvider", () => {
  test("open adds a session, focus tracks it, close removes it", () => {
    let api!: ReturnType<typeof useWorkspaceSessions>;
    render(
      <WorkspaceSessionsProvider>
        <Probe onReady={(a) => (api = a)} />
      </WorkspaceSessionsProvider>,
    );
    act(() => api.open("/ws/a"));
    act(() => api.open("/ws/b"));
    expect(api.openPaths).toEqual(["/ws/a", "/ws/b"]);
    act(() => api.focus("/ws/b"));
    expect(api.focusedPath).toBe("/ws/b");
    act(() => api.close("/ws/a"));
    expect(api.openPaths).toEqual(["/ws/b"]);
  });

  // Guards the delete-then-recreate bug: tearing a workspace down MUST evict its
  // per-path frontend caches (GLB bytes + editor view), otherwise recreating a
  // workspace at the same path re-seeds the viewport with the deleted model
  // (geometry reappears, manifest is gone → "plain materials").
  test("close evicts the per-path artifact + editor caches", () => {
    let api!: ReturnType<typeof useWorkspaceSessions>;
    render(
      <WorkspaceSessionsProvider>
        <Probe onReady={(a) => (api = a)} />
      </WorkspaceSessionsProvider>,
    );
    act(() => api.open("/ws/x"));
    act(() => api.close("/ws/x"));
    expect(clearArtifactCache).toHaveBeenCalledWith("/ws/x");
    expect(clearEditorView).toHaveBeenCalledWith("/ws/x");
  });

  test("closing the focused tab focuses the last remaining tab", () => {
    let api!: ReturnType<typeof useWorkspaceSessions>;
    render(
      <WorkspaceSessionsProvider>
        <Probe onReady={(a) => (api = a)} />
      </WorkspaceSessionsProvider>,
    );
    act(() => api.focus("/ws/a"));
    act(() => api.focus("/ws/b"));
    act(() => api.focus("/ws/c"));
    expect(api.focusedPath).toBe("/ws/c");
    act(() => api.close("/ws/c"));
    expect(api.openPaths).toEqual(["/ws/a", "/ws/b"]);
    expect(api.focusedPath).toBe("/ws/b"); // last remaining
    act(() => api.close("/ws/a")); // closing a NON-focused tab leaves focus alone
    expect(api.focusedPath).toBe("/ws/b");
  });
});

describe("WorkspaceSessionsProvider recentPaths (MRU)", () => {
  test("orders open paths by most-recent focus, floating the just-viewed to the top", () => {
    let api!: ReturnType<typeof useWorkspaceSessions>;
    render(
      <WorkspaceSessionsProvider>
        <Probe onReady={(a) => (api = a)} />
      </WorkspaceSessionsProvider>,
    );
    // Opened but never focused: recency falls back to open order.
    act(() => api.open("/ws/a"));
    act(() => api.open("/ws/b"));
    act(() => api.open("/ws/c"));
    expect(api.recentPaths).toEqual(["/ws/a", "/ws/b", "/ws/c"]);
    // Viewing a workspace floats it to the front; the tab bar order is untouched.
    act(() => api.focus("/ws/b"));
    expect(api.recentPaths).toEqual(["/ws/b", "/ws/a", "/ws/c"]);
    expect(api.openPaths).toEqual(["/ws/a", "/ws/b", "/ws/c"]);
    // Re-viewing the bottom-of-list workspace moves it to the top.
    act(() => api.focus("/ws/c"));
    expect(api.recentPaths).toEqual(["/ws/c", "/ws/b", "/ws/a"]);
  });

  test("seeds the restored focused tab at the front on hydration", () => {
    saveOpenTabs({ open: ["/ws/a", "/ws/b", "/ws/c"], focused: "/ws/b" });
    let api!: ReturnType<typeof useWorkspaceSessions>;
    render(
      <WorkspaceSessionsProvider>
        <Probe onReady={(a) => (api = a)} />
      </WorkspaceSessionsProvider>,
    );
    expect(api.recentPaths[0]).toBe("/ws/b");
  });

  test("drops a closed workspace from the recency order", () => {
    let api!: ReturnType<typeof useWorkspaceSessions>;
    render(
      <WorkspaceSessionsProvider>
        <Probe onReady={(a) => (api = a)} />
      </WorkspaceSessionsProvider>,
    );
    act(() => api.focus("/ws/a"));
    act(() => api.focus("/ws/b"));
    act(() => api.close("/ws/b"));
    expect(api.recentPaths).toEqual(["/ws/a"]);
  });
});

describe("WorkspaceSessionsProvider hydration + wasRestored", () => {
  test("hydrates openPaths and focusedPath from saved state", () => {
    saveOpenTabs({ open: ["/ws/a", "/ws/b"], focused: "/ws/b" });
    let api!: ReturnType<typeof useWorkspaceSessions>;
    render(
      <WorkspaceSessionsProvider>
        <Probe onReady={(a) => (api = a)} />
      </WorkspaceSessionsProvider>,
    );
    expect(api.openPaths).toEqual(["/ws/a", "/ws/b"]);
    expect(api.focusedPath).toBe("/ws/b");
  });

  test("wasRestored returns true for paths from the saved set", () => {
    saveOpenTabs({ open: ["/ws/a", "/ws/b"], focused: "/ws/b" });
    let api!: ReturnType<typeof useWorkspaceSessions>;
    render(
      <WorkspaceSessionsProvider>
        <Probe onReady={(a) => (api = a)} />
      </WorkspaceSessionsProvider>,
    );
    expect(api.wasRestored("/ws/a")).toBe(true);
    expect(api.wasRestored("/ws/b")).toBe(true);
  });

  test("wasRestored returns false for a path opened fresh (not from saved set)", () => {
    saveOpenTabs({ open: ["/ws/a"], focused: "/ws/a" });
    let api!: ReturnType<typeof useWorkspaceSessions>;
    render(
      <WorkspaceSessionsProvider>
        <Probe onReady={(a) => (api = a)} />
      </WorkspaceSessionsProvider>,
    );
    act(() => api.open("/ws/new"));
    expect(api.wasRestored("/ws/new")).toBe(false);
    // original restored path still true
    expect(api.wasRestored("/ws/a")).toBe(true);
  });

  test("starts empty and wasRestored always false when nothing is saved", () => {
    // store is cleared in beforeEach — no saveOpenTabs call here
    let api!: ReturnType<typeof useWorkspaceSessions>;
    render(
      <WorkspaceSessionsProvider>
        <Probe onReady={(a) => (api = a)} />
      </WorkspaceSessionsProvider>,
    );
    expect(api.openPaths).toEqual([]);
    expect(api.focusedPath).toBeNull();
    expect(api.wasRestored("/ws/a")).toBe(false);
  });
});
