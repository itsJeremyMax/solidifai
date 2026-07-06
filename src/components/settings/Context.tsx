/**
 * Settings → Context — the overridable AGENTS.md template editor plus the agent
 * config. Extracted verbatim from the old Settings parent so each settings
 * section owns its own state and can be a route. The only overridable template is
 * AGENTS.md: get_templates() on mount; Save / Reset re-read state so the
 * "edited" badge stays in sync.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Check, FileText, RotateCcw } from "lucide-react";

import {
  getTemplates,
  resetTemplate,
  saveTemplate,
  type Template,
  type TemplateName,
} from "../../lib/workspaces";
import Spinner from "../ui/Spinner";
import { ACCENT_CTA } from "../../lib/styles";
import AgentConfig from "./AgentConfig";

const ICON_STROKE = 1.7;

function FileGlyph({ size = 16 }: { size?: number }) {
  return <FileText size={size} strokeWidth={1.6} />;
}

interface Note {
  kind: "ok" | "err";
  text: string;
}

export default function Context() {
  const [templates, setTemplates] = useState<Template[] | null>(null); // null = loading
  const [selectedName, setSelectedName] = useState<TemplateName | null>(null);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [resetting, setResetting] = useState(false);
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

  // Load templates on mount; auto-select the first (only) one (AGENTS.md).
  useEffect(() => {
    let cancelled = false;
    getTemplates().then((list) => {
      if (cancelled) return;
      setTemplates(list);
      if (list.length > 0) {
        setSelectedName(list[0].name);
        setDraft(list[0].content);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const selected = useMemo(
    () => templates?.find((t) => t.name === selectedName) ?? null,
    [templates, selectedName],
  );

  const dirty = selected !== null && draft !== selected.content;

  // Re-read templates and sync the editor draft to the named template's
  // authoritative content (used after both save and reset).
  const reloadInto = useCallback(async (name: TemplateName) => {
    const list = await getTemplates();
    setTemplates(list);
    const fresh = list.find((t) => t.name === name);
    if (fresh) setDraft(fresh.content);
  }, []);

  const handleSave = useCallback(async () => {
    if (!selected) return;
    const name = selected.name;
    setSaving(true);
    try {
      await saveTemplate(name, draft);
      await reloadInto(name);
      flash({ kind: "ok", text: `Saved ${name}` });
    } catch (e) {
      flash({ kind: "err", text: e instanceof Error ? e.message : `Save failed` });
    } finally {
      setSaving(false);
    }
  }, [selected, draft, reloadInto, flash]);

  const handleReset = useCallback(async () => {
    if (!selected || !selected.isCustom) return;
    const name = selected.name;
    setResetting(true);
    try {
      await resetTemplate(name);
      await reloadInto(name);
      flash({ kind: "ok", text: `Reset ${name} to default` });
    } catch (e) {
      flash({ kind: "err", text: e instanceof Error ? e.message : `Reset failed` });
    } finally {
      setResetting(false);
    }
  }, [selected, reloadInto, flash]);

  const loading = templates === null;
  const busy = saving || resetting;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {/* Context intro */}
      <div className="shrink-0 border-b border-line bg-surface-2 px-6.5 py-4.5">
        <h1 className="text-lg font-bold tracking-snug text-ink">Workspace context</h1>
        <p className="mt-1.25 max-w-160 text-body leading-normal text-ink-2">
          The default agent instructions (AGENTS.md) written into every new workspace, plus which
          skills the coding agent uses. AGENTS.md changes apply to workspaces you create from now
          on.
        </p>
      </div>

      {/* AGENTS.md editor */}
      {selected === null ? (
        <div className="grid flex-1 place-items-center text-body text-ink-3">
          {loading ? "Loading AGENTS.md…" : "No editable template available."}
        </div>
      ) : (
        <>
          <div className="flex shrink-0 items-center gap-3 border-b border-line px-5 py-3">
            <div className="flex items-center gap-2.25">
              <span className="text-ink-3">
                <FileGlyph />
              </span>
              <span className="font-mono text-body font-medium text-ink">{selected.name}</span>
              {selected.isCustom ? (
                <span className="rounded-full bg-accent-tint px-2 py-0.5 font-mono text-micro font-semibold tracking-[0.04em] text-accent">
                  edited
                </span>
              ) : (
                <span className="rounded-full border border-line-2 px-2 py-0.5 font-mono text-micro text-ink-3">
                  default
                </span>
              )}
            </div>

            <div className="flex-1" />

            {note && (
              <span
                className={`font-mono text-caption ${
                  note.kind === "ok" ? "text-engine" : "text-danger"
                }`}
              >
                {note.text}
              </span>
            )}

            <button
              type="button"
              onClick={() => void handleReset()}
              disabled={!selected.isCustom || busy}
              title={selected.isCustom ? "Reset to the shipped default" : "Already at the default"}
              className="inline-flex h-8 items-center gap-1.75 rounded-lg border border-line-2 bg-surface px-3 text-body font-medium text-ink-2 transition-colors duration-150 hover:border-line-3 hover:text-ink disabled:opacity-40 disabled:hover:border-line-2 disabled:hover:text-ink-2"
            >
              {resetting ? (
                <Spinner size={14} />
              ) : (
                <RotateCcw size={14} strokeWidth={ICON_STROKE} />
              )}
              Reset to default
            </button>

            <button
              type="button"
              onClick={() => void handleSave()}
              disabled={!dirty || busy}
              className={`${ACCENT_CTA} h-8 px-3.5 disabled:opacity-45 disabled:hover:bg-accent`}
            >
              {saving ? <Spinner size={14} /> : <Check size={15} strokeWidth={2} />}
              Save
            </button>
          </div>

          <div className="min-h-0 flex-1 p-5">
            <textarea
              value={draft}
              spellCheck={false}
              onChange={(e) => setDraft(e.target.value)}
              className="h-full min-h-70 w-full resize-none rounded-panel border border-line-2 bg-surface-2 p-4 font-mono text-xs leading-[1.65] text-ink shadow-[inset_0_1px_2px_rgba(16,18,24,.04)] outline-none transition-colors duration-150 focus:border-accent focus:bg-surface focus:ring-2 focus:ring-accent-tint"
            />
          </div>
        </>
      )}

      {/* Agent config (enabled skills + runtime settings) */}
      <div className="shrink-0 border-t border-line px-6.5">
        <AgentConfig />
      </div>
    </div>
  );
}
