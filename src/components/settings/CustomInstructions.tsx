/**
 * CustomInstructions — the "Custom instructions" settings section, in both the
 * app (global) and workspace scopes. Plain-language guidance the user writes for
 * the coding agent; Rust weaves it into the workspace's AGENTS.md on the next
 * open. Additive: the global text applies to every workspace, the workspace text
 * layers on top for the focused one. Explicit Save (not auto-save) since this is
 * free prose. The workspace scope needs a focused workspace and degrades to a
 * hint without one.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { Check } from "lucide-react";

import Spinner from "../ui/Spinner";
import { ACCENT_CTA } from "../../lib/styles";
import { getActiveWorkspace } from "../../lib/workspaces";
import {
  getCustomInstructions,
  setCustomInstructions,
  type InstructionScope,
} from "../../lib/customInstructions";

interface Note {
  kind: "ok" | "err";
  text: string;
}

const COPY: Record<InstructionScope, { lead: string; placeholder: string }> = {
  global: {
    lead: "Optional. Your own instructions for the agent in every workspace, added on top of the ones solidifai already provides. Good for things that apply to everything you build, like your printer, materials, or units.",
    placeholder:
      "e.g. I print on an FDM machine in PLA. Prefer M3 hardware. Work in millimetres and add edge breaks to sharp corners.",
  },
  workspace: {
    lead: "Optional. Your own instructions for this workspace, added on top of solidifai's built-in ones and your global instructions. They take effect the next time you open the workspace.",
    placeholder:
      "e.g. This is a housing for an 18650 battery pack. Match the bolt pattern of the existing bracket.",
  },
};

export default function CustomInstructions({ scope }: { scope: InstructionScope }) {
  // Workspace scope needs a focused workspace; global is always ready.
  const [hasWorkspace, setHasWorkspace] = useState(scope === "global");
  const [checkedWorkspace, setCheckedWorkspace] = useState(scope === "global");

  const [saved, setSaved] = useState<string | null>(null); // null = loading
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [note, setNote] = useState<Note | null>(null);
  const noteTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (noteTimer.current) clearTimeout(noteTimer.current);
    },
    [],
  );

  const flash = useCallback((n: Note) => {
    setNote(n);
    if (noteTimer.current) clearTimeout(noteTimer.current);
    noteTimer.current = setTimeout(() => setNote(null), 2800);
  }, []);

  // Confirm a workspace is focused (workspace scope only), then load the text.
  useEffect(() => {
    let cancelled = false;
    async function load() {
      if (scope === "workspace") {
        const ws = await getActiveWorkspace();
        if (cancelled) return;
        setHasWorkspace(!!ws);
        setCheckedWorkspace(true);
        if (!ws) return; // no workspace: skip the load, show the hint
      }
      const text = await getCustomInstructions(scope);
      if (cancelled) return;
      setSaved(text);
      setDraft(text);
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [scope]);

  const dirty = saved !== null && draft !== saved;

  const handleSave = useCallback(async () => {
    if (saved === null || !dirty) return;
    setSaving(true);
    try {
      await setCustomInstructions(scope, draft);
      setSaved(draft);
      flash({ kind: "ok", text: "Saved" });
    } catch (e) {
      flash({ kind: "err", text: e instanceof Error ? e.message : "Save failed" });
    } finally {
      setSaving(false);
    }
  }, [saved, dirty, scope, draft, flash]);

  const copy = COPY[scope];

  return (
    <div className="mx-auto max-w-160 py-6.5">
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <h2 className="text-base font-bold tracking-snug text-ink">Custom instructions</h2>
          <p className="mt-1.25 text-body leading-normal text-ink-2">{copy.lead}</p>
        </div>
        {note && (
          <span
            className={`mt-1 shrink-0 font-mono text-caption ${
              note.kind === "ok" ? "text-engine" : "text-danger"
            }`}
          >
            {note.text}
          </span>
        )}
        <button
          type="button"
          onClick={() => void handleSave()}
          disabled={!dirty || saving}
          className={`${ACCENT_CTA} mt-0.5 h-8 shrink-0 px-3.5 disabled:opacity-45 disabled:hover:bg-accent`}
        >
          {saving ? <Spinner size={14} /> : <Check size={15} strokeWidth={2} />}
          Save
        </button>
      </div>

      {scope === "workspace" && checkedWorkspace && !hasWorkspace ? (
        <div className="mt-4.5 rounded-panel border border-dashed border-line-2 bg-surface-2 px-4 py-4.5 text-center text-body text-ink-3">
          Open a workspace to add instructions for it.
        </div>
      ) : saved === null ? (
        <div className="mt-4.5 text-body text-ink-3">Loading…</div>
      ) : (
        <>
          <textarea
            value={draft}
            spellCheck
            onChange={(e) => setDraft(e.target.value)}
            placeholder={copy.placeholder}
            className="mt-4 h-64 min-h-40 w-full resize-y rounded-panel border border-line-2 bg-surface-2 p-4 text-sm leading-relaxed text-ink shadow-[inset_0_1px_2px_rgba(16,18,24,.04)] outline-none transition-colors duration-150 placeholder:text-ink-3 focus:border-accent focus:bg-surface focus:ring-2 focus:ring-accent-tint"
          />
          <p className="mt-3 text-caption text-ink-3">
            The agent picks these up the next time the workspace opens.
          </p>
        </>
      )}
    </div>
  );
}
