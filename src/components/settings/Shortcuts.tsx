/**
 * Shortcuts — the "Keyboard shortcuts" settings section. A read-only reference
 * card of the app's real bindings (no rebinding yet). Modifier glyphs adapt to
 * the host: ⌘/⇧ on macOS, Ctrl/Shift elsewhere. Every binding here is wired in
 * the codebase (useHistoryKeys, useDismiss, the viewport measure tool, list
 * rows), so the card stays honest.
 */
// Guarded so importing this module doesn't crash in a DOM-less test runtime.
const isMac =
  typeof navigator !== "undefined" &&
  (/Mac/.test(navigator.platform) || /Mac OS X/.test(navigator.userAgent));
const MOD = isMac ? "⌘" : "Ctrl";
const SHIFT = isMac ? "⇧" : "Shift";

interface Shortcut {
  keys: string[];
  label: string;
}

interface Group {
  title: string;
  items: Shortcut[];
}

const GROUPS: Group[] = [
  {
    title: "History",
    items: [
      { keys: [MOD, "Z"], label: "Undo the last edit" },
      { keys: [MOD, SHIFT, "Z"], label: "Redo the last undone edit" },
    ],
  },
  {
    title: "General",
    items: [
      { keys: ["Esc"], label: "Close menus and dialogs, cancel the measure tool" },
      { keys: ["Enter"], label: "Activate the focused control or commit an edit" },
      { keys: ["Space"], label: "Toggle the focused item" },
    ],
  },
];

/** A single mono keycap chip. */
function Keycap({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="inline-flex h-6 min-w-6 items-center justify-center rounded-md border border-line-2 bg-surface-2 px-1.5 font-mono text-caption font-medium text-ink-2 shadow-[inset_0_-1px_0_rgba(18,20,28,.06)]">
      {children}
    </kbd>
  );
}

export default function Shortcuts() {
  return (
    <div className="mx-auto max-w-160 py-6.5">
      <h2 className="text-base font-bold tracking-snug text-ink">Keyboard shortcuts</h2>
      <p className="mt-1.25 text-body leading-normal text-ink-2">
        The bindings available across the app. Rebinding is not supported yet.
      </p>

      <div className="mt-4.5 flex flex-col gap-5">
        {GROUPS.map((group) => (
          <section key={group.title}>
            <div className="mb-2 font-mono text-micro font-semibold uppercase tracking-eyebrow text-ink-3">
              {group.title}
            </div>
            <div className="divide-y divide-line overflow-hidden rounded-panel border border-line bg-surface">
              {group.items.map((s) => (
                <div
                  key={s.label}
                  className="flex items-center gap-4 px-4 py-3 transition-colors duration-150 hover:bg-surface-2"
                >
                  <span className="min-w-0 flex-1 text-body text-ink">{s.label}</span>
                  <span className="flex shrink-0 items-center gap-1">
                    {s.keys.map((k, i) => (
                      <Keycap key={i}>{k}</Keycap>
                    ))}
                  </span>
                </div>
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
