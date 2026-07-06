/**
 * Rail — the 54px collapsed state of the Inspector. One icon button per tab
 * (from the shared {@link INSPECTOR_TABS} registry) plus a vertical "INSPECTOR"
 * label. Clicking a tab icon expands the panel AND switches to that tab; the
 * active icon tracks the current tab.
 */
import { INSPECTOR_TABS, type InspectorTab } from "./tabs";

function RailButton({
  active = false,
  title,
  onClick,
  children,
}: {
  active?: boolean;
  title: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      className={
        active
          ? "grid h-8.5 w-8.5 place-items-center rounded-lg bg-accent-tint text-accent"
          : "grid h-8.5 w-8.5 place-items-center rounded-lg text-ink-3 hover:bg-surface-2 hover:text-ink"
      }
    >
      {children}
    </button>
  );
}

export default function Rail({
  activeTab,
  onExpand,
}: {
  activeTab: InspectorTab;
  onExpand: (t: InspectorTab) => void;
}) {
  return (
    <div className="flex flex-col items-center gap-1.5 py-2.5">
      {INSPECTOR_TABS.map(({ id, label, Icon }) => (
        <RailButton key={id} active={activeTab === id} title={label} onClick={() => onExpand(id)}>
          <Icon size={17} strokeWidth={1.6} />
        </RailButton>
      ))}
      <div className="mt-2 font-mono text-micro tracking-[0.06em] text-ink-3 [writing-mode:vertical-rl]">
        INSPECTOR
      </div>
    </div>
  );
}
