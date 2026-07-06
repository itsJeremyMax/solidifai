import TerminalPane from "./TerminalPane";
import { INTERACTION_SURFACES, type InteractionTab } from "./interaction/surfaces";

export type { InteractionTab };

/**
 * InteractionPanel — left pane. Segmented chip tabs that "sit into" the panel
 * below them, driven by the {@link INTERACTION_SURFACES} registry. The active
 * surface (terminal) is dark with a running dot; a "soon" surface (chat) is muted
 * with a SOON pill and not selectable.
 *
 * `activeTab` is owned by {@link AppShell} so a single source of truth drives both
 * this tab bar and the viewport's empty-state copy.
 */
export default function InteractionPanel({
  activeTab,
  wsPath,
  active,
}: {
  activeTab: InteractionTab;
  wsPath: string;
  active: boolean;
}) {
  return (
    <section className="flex w-[30%] min-w-82.5 flex-col border-r border-line bg-surface-2">
      <div className="relative z-[2] flex gap-1.25 px-3 pt-2.5">
        {INTERACTION_SURFACES.map(({ id, label, Icon, status }) => {
          const soon = status === "soon";
          const selected = status === "active" && activeTab === id;
          return (
            <div
              key={id}
              aria-selected={selected}
              aria-disabled={soon || undefined}
              className={
                selected
                  ? "-mb-px inline-flex h-8.5 items-center gap-2 rounded-t-xl bg-term px-3.5 text-body font-semibold text-white"
                  : soon
                    ? "-mb-px inline-flex h-8.5 cursor-not-allowed items-center gap-2 rounded-t-xl px-3.5 text-body font-semibold text-ink-3 opacity-70"
                    : "-mb-px inline-flex h-8.5 cursor-pointer items-center gap-2 rounded-t-xl px-3.5 text-body font-semibold text-ink-3 opacity-70"
              }
            >
              {selected && id === "terminal" && (
                <span className="h-1.75 w-1.75 rounded-full bg-engine shadow-[0_0_6px_rgba(25,169,87,.7)]" />
              )}
              <Icon size={15} strokeWidth={1.7} />
              {label}
              {soon && (
                <span className="rounded-full bg-accent-tint px-1.5 py-px font-mono text-micro font-semibold tracking-[0.06em] text-accent">
                  SOON
                </span>
              )}
            </div>
          );
        })}
      </div>

      <TerminalPane wsPath={wsPath} active={active} />
    </section>
  );
}
