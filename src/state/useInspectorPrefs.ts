/**
 * useInspectorPrefs — persists the Inspector's layout (active tab + open
 * sections, keys namespaced by tab) to localStorage. Pure UI state; guarded
 * reads fall back to defaults, writes are best-effort.
 */
import { useCallback, useState } from "react";
import { isInspectorTab, type InspectorTab } from "../components/inspector/tabs";

const TAB_KEY = "solidifai.inspector.tab";
const SECTIONS_KEY = "solidifai.inspector.sections";

export const DEFAULT_OPEN = {
  "model.parts": true,
  "model.parameters": true,
  "model.explore": false,
  "model.measure": false,
  "checks.goals": true,
  "checks.dfm": true,
  "checks.stress": true,
  "checks.fit": false,
  "activity.brief": true,
  "activity.history": true,
  "make.estimate": true,
  "make.orient": false,
} as const satisfies Record<string, boolean>;

export type SectionKey = keyof typeof DEFAULT_OPEN;
export type SectionState = Record<SectionKey, boolean>;

function readTab(): InspectorTab {
  try {
    const t = localStorage.getItem(TAB_KEY);
    return isInspectorTab(t) ? t : "model";
  } catch {
    return "model";
  }
}

function readOpen(): SectionState {
  const open: SectionState = { ...DEFAULT_OPEN };
  try {
    const raw = localStorage.getItem(SECTIONS_KEY);
    if (!raw) return open;
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    for (const key of Object.keys(open) as SectionKey[]) {
      if (typeof parsed[key] === "boolean") open[key] = parsed[key];
    }
  } catch {
    /* defaults stand */
  }
  return open;
}

export function useInspectorPrefs() {
  const [tab, setTabState] = useState<InspectorTab>(readTab);
  const [open, setOpen] = useState<SectionState>(readOpen);

  const setTab = useCallback((t: InspectorTab) => {
    setTabState(t);
    try {
      localStorage.setItem(TAB_KEY, t);
    } catch {
      /* best-effort */
    }
  }, []);

  const toggleSection = useCallback((k: SectionKey) => {
    setOpen((prev) => {
      const next = { ...prev, [k]: !prev[k] };
      try {
        localStorage.setItem(SECTIONS_KEY, JSON.stringify(next));
      } catch {
        /* best-effort */
      }
      return next;
    });
  }, []);

  return { tab, setTab, open, toggleSection };
}
