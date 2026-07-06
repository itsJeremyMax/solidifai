import {
  Boxes,
  ClipboardList,
  Gauge,
  History as HistoryIcon,
  Printer,
  Scale,
  Target,
} from "lucide-react";

/**
 * Inspector tab registry — the single source of truth for the Inspector's tabs.
 * The segmented control ({@link InspectorTabs}), the collapsed {@link Rail}, and
 * the persisted-tab validation in `useInspectorPrefs` all derive from this list,
 * so adding a tab (as the merged "Make" tab would have been) is one entry here,
 * not three edits. Selection stays in `useInspectorPrefs` (persisted), not the URL.
 */
export type InspectorTab =
  "plan" | "model" | "requirements" | "measure" | "dfm" | "history" | "make";

export interface InspectorTabDef {
  id: InspectorTab;
  label: string;
  Icon: typeof Boxes;
}

export const INSPECTOR_TABS: InspectorTabDef[] = [
  { id: "plan", label: "Plan", Icon: ClipboardList },
  { id: "model", label: "Model", Icon: Boxes },
  { id: "requirements", label: "Requirements", Icon: Target },
  { id: "measure", label: "Measure", Icon: Scale },
  { id: "dfm", label: "DFM", Icon: Gauge },
  { id: "history", label: "History", Icon: HistoryIcon },
  { id: "make", label: "Make", Icon: Printer },
];

const IDS = new Set<string>(INSPECTOR_TABS.map((t) => t.id));

/** Narrowing guard for persisted/untrusted values. */
export function isInspectorTab(v: unknown): v is InspectorTab {
  return typeof v === "string" && IDS.has(v);
}
