import type { Material } from "../lib/materials";

/** Per-workspace editor view-state, restored across tab switches so the inspector
 *  + selection don't reset (and the sidebar doesn't slide in) when a session's
 *  EditorPanes remounts on refocus. Module-level: persists for the app run. */
export interface EditorViewSnapshot {
  inspectorCollapsed: boolean;
  /** Whether the one-time "reveal the inspector when a model first appears" fired. */
  revealed: boolean;
  selectedId: string | null;
  hiddenIds: string[];
  explode: number;
  materialOverrides: Record<string, Material>;
}

const STORE = new Map<string, EditorViewSnapshot>();
export const readEditorView = (wsPath: string): EditorViewSnapshot | undefined => STORE.get(wsPath);
export const writeEditorView = (wsPath: string, snap: EditorViewSnapshot): void =>
  void STORE.set(wsPath, snap);
export const clearEditorView = (wsPath: string): void => void STORE.delete(wsPath);
