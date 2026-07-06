/**
 * useInspectorPrefs — persists the Inspector's *layout* (active tab + which Model
 * sections are open) to localStorage. Pure UI state, so it deliberately does NOT
 * touch the Rust-backed appConfig. Reads are guarded → defaults on missing/bad
 * JSON; writes are best-effort.
 */
import { useCallback, useState } from "react";
import { isInspectorTab, type InspectorTab } from "../components/inspector/tabs";

export type SectionKey = "parts" | "parameters" | "dimensions" | "explore";

const TAB_KEY = "solidifai.inspector.tab";
const SECTIONS_KEY = "solidifai.inspector.sections";

const DEFAULT_OPEN: Record<SectionKey, boolean> = {
  parts: true,
  parameters: true,
  dimensions: false,
  explore: false,
};

function readTab(): InspectorTab {
  try {
    const t = localStorage.getItem(TAB_KEY);
    return isInspectorTab(t) ? t : "model";
  } catch {
    return "model";
  }
}

function readOpen(): Record<SectionKey, boolean> {
  try {
    const raw = localStorage.getItem(SECTIONS_KEY);
    if (!raw) return { ...DEFAULT_OPEN };
    const parsed = JSON.parse(raw) as Partial<Record<SectionKey, boolean>>;
    return {
      parts: typeof parsed.parts === "boolean" ? parsed.parts : DEFAULT_OPEN.parts,
      parameters:
        typeof parsed.parameters === "boolean" ? parsed.parameters : DEFAULT_OPEN.parameters,
      dimensions:
        typeof parsed.dimensions === "boolean" ? parsed.dimensions : DEFAULT_OPEN.dimensions,
      explore: typeof parsed.explore === "boolean" ? parsed.explore : DEFAULT_OPEN.explore,
    };
  } catch {
    return { ...DEFAULT_OPEN };
  }
}

export function useInspectorPrefs() {
  const [tab, setTabState] = useState<InspectorTab>(readTab);
  const [open, setOpen] = useState<Record<SectionKey, boolean>>(readOpen);

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
