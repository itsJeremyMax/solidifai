import { useCallback, useRef, useState } from "react";
import { Pencil, X } from "lucide-react";
import { tildePath, type Workspace } from "../../lib/workspaces";
import Spinner from "../ui/Spinner";
import { ACCENT_CTA } from "../../lib/styles";
import { ModalShell } from "./ModalShell";

const ICON_STROKE = 1.7;
const DESC_MAX = 280;
const TAG_MAX = 12;

/** Normalize a raw tag string: lowercase, trimmed. */
function normalizeTag(raw: string): string {
  return raw.trim().toLowerCase();
}

/** Edit-details dialog — name, description, and tags for a workspace. */
export function EditDetailsDialog({
  ws,
  busy,
  onSubmit,
  onClose,
}: {
  ws: Workspace;
  busy: boolean;
  onSubmit: (payload: {
    name: string;
    description: string;
    tags: string[];
  }) => Promise<string | null>;
  onClose: () => void;
}) {
  const [name, setName] = useState(ws.name);
  const [description, setDescription] = useState(ws.description ?? "");
  const [tags, setTags] = useState<string[]>(ws.tags);
  const [tagInput, setTagInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const tagInputRef = useRef<HTMLInputElement>(null);

  const trimmedName = name.trim();
  const canSubmit = trimmedName.length > 0 && !busy;

  /** Add a tag from the current input value (if valid + not duplicate). */
  const commitTag = useCallback(() => {
    const tag = normalizeTag(tagInput);
    if (!tag) {
      setTagInput("");
      return;
    }
    if (tags.length >= TAG_MAX) {
      setTagInput("");
      return;
    }
    if (!tags.includes(tag)) {
      setTags((prev) => [...prev, tag]);
    }
    setTagInput("");
  }, [tagInput, tags]);

  const removeTag = useCallback((tag: string) => {
    setTags((prev) => prev.filter((t) => t !== tag));
  }, []);

  const submit = useCallback(async () => {
    if (trimmedName.length === 0) {
      setError("Enter a workspace name.");
      return;
    }
    const err = await onSubmit({
      name: trimmedName,
      description: description.trim(),
      tags,
    });
    if (err) setError(err);
  }, [trimmedName, description, tags, onSubmit]);

  return (
    <ModalShell onClose={onClose} labelledBy="edit-details-title">
      {/* Header */}
      <div className="mb-4 flex items-center gap-2.5">
        <span className="grid h-8.5 w-8.5 shrink-0 place-items-center rounded-xl border border-line-2 bg-surface-2 text-accent">
          <Pencil size={17} strokeWidth={ICON_STROKE} />
        </span>
        <h2 id="edit-details-title" className="text-base font-bold tracking-snug text-ink">
          Edit details
        </h2>
      </div>

      {/* Name field */}
      <label className="mb-3.5 block">
        <span className="mb-1.5 block text-micro font-bold uppercase tracking-eyebrow text-ink-3">
          Name
        </span>
        <input
          type="text"
          value={name}
          autoFocus
          spellCheck={false}
          onChange={(e) => {
            setName(e.target.value);
            if (error) setError(null);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && canSubmit) void submit();
          }}
          className="h-9.5 w-full rounded-lg border border-line-2 bg-surface-2 px-3 text-sm text-ink outline-none transition-colors duration-150 placeholder:text-ink-3 focus:border-accent focus:bg-surface focus:ring-2 focus:ring-accent-tint"
        />
      </label>

      {/* Description field */}
      <label className="mb-3.5 block">
        <span className="mb-1.5 block text-micro font-bold uppercase tracking-eyebrow text-ink-3">
          Description
        </span>
        <textarea
          value={description}
          maxLength={DESC_MAX}
          rows={3}
          placeholder="What is this workspace for?"
          onChange={(e) => setDescription(e.target.value)}
          className="w-full resize-none rounded-lg border border-line-2 bg-surface-2 px-3 py-2 text-sm text-ink outline-none transition-colors duration-150 placeholder:text-ink-3 focus:border-accent focus:bg-surface focus:ring-2 focus:ring-accent-tint"
        />
        <span className="mt-0.75 block text-right text-micro text-ink-3">
          {description.length}/{DESC_MAX}
        </span>
      </label>

      {/* Tags field */}
      <div className="mb-4">
        <span className="mb-1.5 block text-micro font-bold uppercase tracking-eyebrow text-ink-3">
          Tags
        </span>

        {/* Chip + input area */}
        <div
          role="group"
          aria-label="Tags"
          onClick={() => tagInputRef.current?.focus()}
          className="flex min-h-9.5 w-full cursor-text flex-wrap gap-1.5 rounded-lg border border-line-2 bg-surface-2 px-2.5 py-2 transition-colors duration-150 focus-within:border-accent focus-within:bg-surface focus-within:ring-2 focus-within:ring-accent-tint"
        >
          {tags.map((tag) => (
            <span
              key={tag}
              className="inline-flex items-center gap-1 rounded-full border border-line-2 bg-surface px-2 py-0.5 text-micro font-semibold text-ink-2"
            >
              {tag}
              <button
                type="button"
                aria-label={`Remove tag ${tag}`}
                onClick={(e) => {
                  e.stopPropagation();
                  removeTag(tag);
                }}
                className="grid place-items-center rounded-full text-ink-3 transition-colors duration-100 hover:text-ink focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent-line"
              >
                <X size={10} strokeWidth={2.2} />
              </button>
            </span>
          ))}

          {tags.length < TAG_MAX && (
            <input
              ref={tagInputRef}
              type="text"
              value={tagInput}
              placeholder={tags.length === 0 ? "Add tags…" : ""}
              onChange={(e) => setTagInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === ",") {
                  e.preventDefault();
                  commitTag();
                } else if (e.key === "Backspace" && tagInput === "" && tags.length > 0) {
                  // Remove last tag on backspace when input is empty
                  setTags((prev) => prev.slice(0, -1));
                }
              }}
              onBlur={commitTag}
              className="min-w-24 flex-1 bg-transparent text-sm text-ink outline-none placeholder:text-ink-3"
            />
          )}
        </div>

        <p className="mt-0.75 text-micro text-ink-3">
          Press Enter or comma to add. Up to {TAG_MAX} tags.
        </p>
      </div>

      {/* Path */}
      <p className="mb-4 truncate font-mono text-caption text-ink-3">{tildePath(ws.path)}</p>

      {/* Error */}
      {error && (
        <div className="mb-3.5 rounded-lg border border-danger-line bg-danger-bg px-3 py-2.25 font-mono text-caption text-danger">
          {error}
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center justify-end gap-2.25">
        <button
          type="button"
          onClick={onClose}
          disabled={busy}
          className="inline-flex h-9 items-center rounded-lg px-3.5 text-body font-medium text-ink-2 transition-colors duration-150 hover:bg-surface-2 hover:text-ink disabled:opacity-50"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={() => void submit()}
          disabled={!canSubmit}
          className={`${ACCENT_CTA} h-9 px-4 disabled:opacity-45 disabled:hover:bg-accent`}
        >
          {busy ? <Spinner /> : <Pencil size={14} strokeWidth={ICON_STROKE} />}
          {busy ? "Saving…" : "Save"}
        </button>
      </div>
    </ModalShell>
  );
}
