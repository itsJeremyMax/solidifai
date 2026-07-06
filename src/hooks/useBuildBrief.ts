import { useEffect, useState } from "react";

import { getBuildBrief, onBuildBriefUpdated } from "../lib/ipc";

export interface BuildBriefPart {
  name: string;
  role: string;
  why: string;
}
export interface BuildBriefDim {
  name: string;
  value: number | null;
  unit: string;
  drives?: string;
}
export interface BuildBriefInterface {
  between: [string, string];
  kind: string;
  clearance: number | null;
}
export interface BuildBrief {
  summary: string;
  parts: BuildBriefPart[];
  key_dims: BuildBriefDim[];
  interfaces: BuildBriefInterface[];
  make_real: string;
  tier: "skip" | "stream" | "pause";
}

/**
 * Focused-workspace build brief, refreshed when the engine writes build_brief.json.
 * `getBuildBrief` already returns parsed JSON (or null), so a missing/unparseable
 * file simply yields null and the panel shows its empty state.
 */
export function useBuildBrief(wsPath: string | null): BuildBrief | null {
  const [brief, setBrief] = useState<BuildBrief | null>(null);
  useEffect(() => {
    let cancelled = false;
    let unlisten: (() => void) | undefined;
    const refresh = () => {
      if (!wsPath) {
        setBrief(null);
        return;
      }
      void getBuildBrief(wsPath)
        .then((raw) => {
          if (!cancelled) setBrief((raw as BuildBrief) ?? null);
        })
        .catch(() => {
          if (!cancelled) setBrief(null);
        });
    };
    refresh();
    onBuildBriefUpdated((p) => {
      if (!wsPath || p.wsId === wsPath) refresh();
    })
      .then((fn) => {
        if (cancelled) fn();
        else unlisten = fn;
      })
      .catch(() => {});
    return () => {
      cancelled = true;
      unlisten?.();
    };
  }, [wsPath]);
  return brief;
}
