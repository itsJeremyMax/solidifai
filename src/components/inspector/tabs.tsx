import { Activity, Boxes, ListChecks, Printer } from "lucide-react";

/**
 * Inspector tab registry — single source of truth; the segmented control, the
 * collapsed Rail, and the persisted-tab validation all derive from this list.
 */
export type InspectorTab = "model" | "checks" | "activity" | "make";

export interface InspectorTabDef {
  id: InspectorTab;
  label: string;
  Icon: typeof Boxes;
}

export const INSPECTOR_TABS: InspectorTabDef[] = [
  { id: "model", label: "Model", Icon: Boxes },
  { id: "checks", label: "Checks", Icon: ListChecks },
  { id: "activity", label: "Activity", Icon: Activity },
  { id: "make", label: "Make", Icon: Printer },
];

const IDS = new Set<string>(INSPECTOR_TABS.map((t) => t.id));

/** Narrowing guard for persisted/untrusted values (stale pre-consolidation ids
 *  like "dfm" simply fail and the caller falls back to the default tab). */
export function isInspectorTab(v: unknown): v is InspectorTab {
  return typeof v === "string" && IDS.has(v);
}
