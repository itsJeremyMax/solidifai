import { useEffect, useState } from "react";
import { getWorkspaceMeta, onWorkspaceMetaUpdated } from "../lib/ipc";

export interface WorkspaceMeta {
  name: string;
  description: string;
  tags: string[];
  proposedName: string | null;
}

function parse(raw: string | null): WorkspaceMeta | null {
  if (!raw) return null;
  try {
    const v = JSON.parse(raw);
    const m = v?.metadata ?? v;
    return {
      name: typeof m?.name === "string" ? m.name : "",
      description: typeof m?.description === "string" ? m.description : "",
      tags: Array.isArray(m?.tags) ? m.tags.filter((t: unknown) => typeof t === "string") : [],
      proposedName: typeof m?.proposedName === "string" ? m.proposedName : null,
    };
  } catch {
    return null;
  }
}

/** Focused-workspace metadata, refreshed when the engine/Sol writes workspace.json. */
export function useWorkspaceMeta(wsPath: string | null): WorkspaceMeta | null {
  const [meta, setMeta] = useState<WorkspaceMeta | null>(null);
  useEffect(() => {
    let cancelled = false;
    let unlisten: (() => void) | undefined;
    const refresh = () => {
      void getWorkspaceMeta().then((raw) => {
        if (!cancelled) setMeta(parse(raw));
      });
    };
    refresh();
    onWorkspaceMetaUpdated((p) => {
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
  return meta;
}
