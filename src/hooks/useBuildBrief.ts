import { useEffect, useState } from "react";

import { getBuildBrief, onBuildBriefUpdated } from "../lib/ipc/workspace";

export interface BuildBriefPart {
  id: string;
  name: string;
  role: string;
  why: string;
  children?: string[];
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
  schema: 1 | 2;
  revision?: number;
  summary: string;
  parts: BuildBriefPart[];
  key_dims: BuildBriefDim[];
  interfaces: BuildBriefInterface[];
  make_real: string;
  tier: "skip" | "stream" | "pause";
  /** Unchanged v2 data for consumers that need hierarchy, risk, or evidence. */
  raw?: Record<string, unknown>;
}

const asRecord = (value: unknown): Record<string, unknown> | null =>
  value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;

const asRows = (value: unknown): Record<string, unknown>[] =>
  Array.isArray(value)
    ? value.map(asRecord).filter((row): row is Record<string, unknown> => row !== null)
    : [];

const text = (value: unknown): string => (typeof value === "string" ? value : "");
const numberOrNull = (value: unknown): number | null =>
  typeof value === "number" && Number.isFinite(value) ? value : null;

/** Convert either persisted schema to rows the read-only panel can render safely. */
export function projectBuildBrief(value: unknown): BuildBrief | null {
  const raw = asRecord(value);
  if (!raw || !text(raw.summary) || !["skip", "stream", "pause"].includes(text(raw.tier)))
    return null;
  const schema = raw.schema === 2 ? 2 : 1;
  const parts = asRows(raw.parts).map((part, index) => ({
    id: text(part.id) || text(part.name) || `part-${index + 1}`,
    name: text(part.name) || "Unnamed part",
    role: text(part.role),
    why: text(part.why),
    ...(schema === 2 && Array.isArray(part.children)
      ? { children: part.children.filter((child): child is string => typeof child === "string") }
      : {}),
  }));
  const dimensions = schema === 2 ? asRows(raw.dimensions) : asRows(raw.key_dims);
  const interfaces = asRows(raw.interfaces).map((item) => ({
    between:
      schema === 2
        ? ([...(Array.isArray(item.participants) ? item.participants : [])]
            .filter((participant): participant is string => typeof participant === "string")
            .slice(0, 2) as [string, string])
        : ((Array.isArray(item.between) ? item.between.slice(0, 2) : []) as [string, string]),
    kind: text(item.kind) || "unspecified",
    clearance: numberOrNull(item.clearance),
  }));
  return {
    schema,
    ...(schema === 2 && typeof raw.revision === "number" ? { revision: raw.revision, raw } : {}),
    summary: text(raw.summary),
    parts,
    key_dims: dimensions.map((dim) => ({
      name: text(dim.name) || "Unnamed dimension",
      value: numberOrNull(dim.value),
      unit: text(dim.unit) || "mm",
      ...(text(dim.drives) ? { drives: text(dim.drives) } : {}),
    })),
    interfaces,
    make_real: schema === 1 ? text(raw.make_real) : text(asRows(raw.manufacturing)[0]?.description),
    tier: raw.tier as BuildBrief["tier"],
  };
}

/**
 * Focused-workspace build brief, refreshed when the engine writes build_brief.json.
 * `getBuildBrief` already returns parsed JSON (or null), so a missing/unparseable
 * file simply yields null and the panel shows its empty state.
 *
 * `rev` counts live file-watch updates only (never the initial fetch), so a
 * consumer can tell "Sol just published a brief" apart from "an old brief loaded".
 */
export function useBuildBrief(wsPath: string | null): { brief: BuildBrief | null; rev: number } {
  const [brief, setBrief] = useState<BuildBrief | null>(null);
  const [rev, setRev] = useState(0);
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
          if (!cancelled) setBrief(projectBuildBrief(raw));
        })
        .catch(() => {
          if (!cancelled) setBrief(null);
        });
    };
    refresh();
    onBuildBriefUpdated((p) => {
      if (!wsPath || p.wsId === wsPath) {
        if (!cancelled) setRev((r) => r + 1);
        refresh();
      }
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
  return { brief, rev };
}
