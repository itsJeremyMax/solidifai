import { describe, it, expect, beforeEach } from "vitest";
import {
  readEditorView,
  writeEditorView,
  clearEditorView,
  type EditorViewSnapshot,
} from "./editorViewState";

const WS = "/ws/test-editorview";

const snap: EditorViewSnapshot = {
  inspectorCollapsed: false,
  revealed: true,
  selectedId: "part-1",
  hiddenIds: ["part-2"],
  explode: 42,
  materialOverrides: {
    "part-1": {
      id: "aluminum",
      label: "Aluminum",
      base: "aluminum",
      colorHex: "#a8a8a8",
      finish: "metallic",
    },
  },
};

beforeEach(() => {
  clearEditorView(WS);
});

describe("editorViewState", () => {
  it("returns undefined before any write", () => {
    expect(readEditorView(WS)).toBeUndefined();
  });

  it("round-trips a snapshot through write then read", () => {
    writeEditorView(WS, snap);
    expect(readEditorView(WS)).toEqual(snap);
  });

  it("clear removes the stored snapshot", () => {
    writeEditorView(WS, snap);
    clearEditorView(WS);
    expect(readEditorView(WS)).toBeUndefined();
  });

  it("write overwrites a previous snapshot", () => {
    writeEditorView(WS, snap);
    const updated: EditorViewSnapshot = { ...snap, inspectorCollapsed: true, selectedId: null };
    writeEditorView(WS, updated);
    expect(readEditorView(WS)?.inspectorCollapsed).toBe(true);
    expect(readEditorView(WS)?.selectedId).toBeNull();
  });

  it("isolated by wsPath — writes to one path do not affect another", () => {
    const other = "/ws/other-editorview";
    writeEditorView(WS, snap);
    expect(readEditorView(other)).toBeUndefined();
    clearEditorView(other); // no-op; shouldn't throw
    expect(readEditorView(WS)).toEqual(snap);
  });
});
