import { describe, expect, it } from "vitest";
import type { Workspace } from "./workspaces";
import { selectWorkspaces, heroWorkspace, isRecent, lastActiveAt, RECENT_WINDOW_MS } from "./home";

const NOW = 1_000_000_000_000;
const ws = (over: Partial<Workspace> & { path: string }): Workspace => ({
  name: over.path.slice(1),
  createdAt: NOW - 1000,
  lastOpenedAt: null,
  archivedAt: null,
  description: null,
  tags: [],
  proposedName: null,
  ...over,
});

describe("selectWorkspaces", () => {
  const a = ws({ path: "/a", lastOpenedAt: NOW - 1000 }); // active, recent
  const b = ws({ path: "/b", lastOpenedAt: NOW - 3000 }); // active, older
  const old = ws({ path: "/old", lastOpenedAt: NOW - RECENT_WINDOW_MS - 1 }); // active, not recent
  const arc = ws({ path: "/arc", archivedAt: NOW - 500 }); // archived
  const all = [b, a, old, arc];

  it("All: active only, newest-active first, with counts", () => {
    const r = selectWorkspaces({ workspaces: all, thumbs: {}, filter: "all", query: "", now: NOW });
    expect(r.visible.map((w) => w.path)).toEqual(["/a", "/b", "/old"]);
    expect(r.counts).toEqual({ all: 3, archived: 1 });
  });

  it("Recent: active within the window", () => {
    const r = selectWorkspaces({
      workspaces: all,
      thumbs: {},
      filter: "recent",
      query: "",
      now: NOW,
    });
    expect(r.visible.map((w) => w.path)).toEqual(["/a", "/b"]);
  });

  it("Archived: archived only, newest-archived first", () => {
    const r = selectWorkspaces({
      workspaces: all,
      thumbs: {},
      filter: "archived",
      query: "",
      now: NOW,
    });
    expect(r.visible.map((w) => w.path)).toEqual(["/arc"]);
  });

  it("search filters by name within the current set, case-insensitive", () => {
    const r = selectWorkspaces({
      workspaces: all,
      thumbs: {},
      filter: "all",
      query: "A",
      now: NOW,
    });
    expect(r.visible.map((w) => w.path)).toEqual(["/a"]);
  });

  it("thumbnail capturedAt counts toward recency", () => {
    expect(isRecent(old, NOW, { capturedAt: NOW - 10, partCount: 1 })).toBe(true);
    expect(lastActiveAt(old, { capturedAt: NOW - 10, partCount: 1 })).toBe(NOW - 10);
  });

  it("14d boundary is inclusive", () => {
    const edge = ws({ path: "/edge", lastOpenedAt: NOW - RECENT_WINDOW_MS });
    expect(isRecent(edge, NOW)).toBe(true);
  });

  it("matches query against description and tags, not just name", () => {
    const list = [
      ws({ path: "/alpha", name: "Alpha", description: "a planetary reducer" }),
      ws({ path: "/beta", name: "Beta", tags: ["bearing", "press-fit"] }),
      ws({ path: "/gamma", name: "Gamma" }),
    ];
    const base = { thumbs: {}, filter: "all" as const, now: 100 };
    expect(
      selectWorkspaces({ ...base, workspaces: list, query: "planetary" }).visible.map(
        (w) => w.name,
      ),
    ).toEqual(["Alpha"]);
    expect(
      selectWorkspaces({ ...base, workspaces: list, query: "bearing" }).visible.map((w) => w.name),
    ).toEqual(["Beta"]);
  });

  it("filters to a single tag when tagFilter is set", () => {
    const list = [
      ws({ path: "/A", name: "A", tags: ["gears"] }),
      ws({ path: "/B", name: "B", tags: ["bearing"] }),
      ws({ path: "/C", name: "C", tags: ["gears", "petg"] }),
    ];
    const res = selectWorkspaces({
      workspaces: list,
      thumbs: {},
      filter: "all",
      query: "",
      now: 1,
      tagFilter: "gears",
    });
    expect(res.visible.map((w) => w.name)).toEqual(["A", "C"]);
  });

  it("empty list yields no visible and zero counts", () => {
    const r = selectWorkspaces({ workspaces: [], thumbs: {}, filter: "all", query: "", now: NOW });
    expect(r.visible).toEqual([]);
    expect(r.counts).toEqual({ all: 0, archived: 0 });
    expect(
      heroWorkspace({ workspaces: [], thumbs: {}, filter: "all", query: "", now: NOW }),
    ).toBeNull();
  });
});

describe("heroWorkspace", () => {
  const a = ws({ path: "/a", lastOpenedAt: NOW - 1000 });
  const b = ws({ path: "/b", lastOpenedAt: NOW - 50 });
  it("is the newest-active workspace in the default view", () => {
    expect(
      heroWorkspace({ workspaces: [a, b], thumbs: {}, filter: "all", query: "", now: NOW })?.path,
    ).toBe("/b");
  });
  it("is null when searching or not on All, or when none active", () => {
    expect(
      heroWorkspace({ workspaces: [a, b], thumbs: {}, filter: "all", query: "x", now: NOW }),
    ).toBeNull();
    expect(
      heroWorkspace({ workspaces: [a, b], thumbs: {}, filter: "recent", query: "", now: NOW }),
    ).toBeNull();
    expect(
      heroWorkspace({
        workspaces: [ws({ path: "/z", archivedAt: NOW })],
        thumbs: {},
        filter: "all",
        query: "",
        now: NOW,
      }),
    ).toBeNull();
  });
});
