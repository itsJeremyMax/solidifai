/**
 * WorkspaceSwitcher — the segmented tab control that lives inline in the app
 * header. It is the everyday way to move between open workspaces and it folds in
 * two responsibilities the header used to spread across separate chrome: the old
 * breadcrumb (the focused pill IS the workspace identity) and the standalone
 * engine status pill (each tab carries its own status dot).
 *
 * Visual contract (matches the approved mockup, `.../content/c-refined.html`):
 *   • a `bg-surface-2` rounded container (border-line, 3px pad) of pills
 *   • Focused pill: white `bg-surface` lift + cobalt inset ring + accent text
 *   • Ready: green dot · Error: red dot · Provisioning/building: amber spinner
 *     plus a thin animated underline shimmer so a busy tab still pulls the eye
 *   • Hover reveals a × (also middle-click) to close the tab
 *   • Past 5 tabs the rest collapse into a `+N ⌄` chip → popover; the chip wears
 *     a status dot if any collapsed tab is non-ready, so a busy hidden tab shows
 *
 * The component is presentational: open paths, the focused path, display names,
 * and per-tab statuses come in as props; focus / close / add go out as
 * callbacks. {@link WorkspaceSwitcherBar} is the connected wrapper.
 */
import { useEffect, useState, type MouseEvent } from "react";
import { ChevronDown, Loader2 } from "lucide-react";
import { useMatch, useNavigate } from "react-router-dom";

import { useDismiss } from "../hooks/useDismiss";
import { useWorkspaceStatuses } from "../hooks/useEngineStatus";
import { useWorkspaceSessions } from "../state/workspaceSessions";
import { listWorkspaces, closeWorkspaceTab } from "../lib/workspaces";
import { editorPath } from "../lib/routes";

/** A tab's engine status, as carried per-`wsId` on the `engine-status` event.
 *  Mirrors the canonical `EngineStatus`; `updating` (a global engine-binary
 *  download) renders like `provisioning` on the rare chance it arrives tab-scoped. */
export type WorkspaceStatusKind = "provisioning" | "updating" | "ready" | "error";

/** How many pills stay visible before the rest collapse into the overflow chip. */
const MAX_VISIBLE = 5;

export interface WorkspaceSwitcherProps {
  /** Open workspace paths, in tab order. */
  openPaths: string[];
  /** The focused workspace path, or null when none is focused. */
  focusedPath: string | null;
  /** path -> display name (caller resolves; fallback handled upstream). */
  names: Record<string, string>;
  /** path -> engine status; a missing entry renders an idle (no) dot. */
  statuses: Record<string, WorkspaceStatusKind>;
  onFocus: (path: string) => void;
  onClose: (path: string) => void;
  onAdd: () => void;
}

/**
 * The status atom shown at a pill's leading edge. Provisioning shows a small
 * amber spinner (the "building" treatment); ready/error are solid dots. A focused
 * pill is identified by the pill's own white lift + cobalt ring, so when a
 * focused tab has no known status we still show the accent dot as its identity.
 */
function StatusDot({ status, focused }: { status?: WorkspaceStatusKind; focused: boolean }) {
  if (status === "provisioning" || status === "updating") {
    return (
      <Loader2
        size={11}
        strokeWidth={2.2}
        className="shrink-0 animate-spin text-amber"
        aria-hidden
      />
    );
  }
  const color =
    status === "ready"
      ? "bg-engine"
      : status === "error"
        ? "bg-danger-bold"
        : focused
          ? "bg-accent"
          : "bg-ink-3";
  return <span aria-hidden className={`h-1.75 w-1.75 shrink-0 rounded-full ${color}`} />;
}

/** One segmented pill: status dot + name, with a hover/middle-click close. */
function Pill({
  path,
  name,
  status,
  focused,
  onFocus,
  onClose,
}: {
  path: string;
  name: string;
  status?: WorkspaceStatusKind;
  focused: boolean;
  onFocus: (path: string) => void;
  onClose: (path: string) => void;
}) {
  const building = status === "provisioning";

  // Middle-click closes the tab (browser convention). Guard the default so the
  // OS autoscroll cursor never appears.
  const onMouseDown = (e: MouseEvent) => {
    if (e.button === 1) {
      e.preventDefault();
      onClose(path);
    }
  };

  return (
    <button
      type="button"
      aria-pressed={focused}
      title={name}
      onClick={() => onFocus(path)}
      onMouseDown={onMouseDown}
      className={`group/pill relative flex h-6.5 items-center gap-1.75 whitespace-nowrap rounded-md px-2.75 text-caption tracking-snug transition-colors duration-100 ${
        focused
          ? "bg-surface font-semibold text-accent shadow-[0_1px_2px_rgba(16,18,24,.12),inset_0_0_0_1px_var(--color-accent-line)]"
          : "font-medium text-ink-2 hover:bg-surface-hover"
      }`}
    >
      <StatusDot status={status} focused={focused} />
      <span>{name}</span>
      {/* Hover-revealed close. Always in the DOM (opacity-gated) so it stays
          clickable for tests and keyboard focus; stopPropagation keeps it from
          also focusing the tab. */}
      <span
        role="button"
        aria-label={`Close ${name}`}
        tabIndex={0}
        onClick={(e) => {
          e.stopPropagation();
          onClose(path);
        }}
        onMouseDown={(e) => e.stopPropagation()}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            e.stopPropagation();
            onClose(path);
          }
        }}
        className="-mr-0.75 ml-0.25 grid h-3.25 w-3.25 place-items-center rounded text-ink-3 opacity-0 transition-opacity duration-100 hover:bg-line-2 hover:text-ink focus-visible:opacity-100 group-hover/pill:opacity-100"
      >
        <svg width="9" height="9" viewBox="0 0 9 9" aria-hidden fill="none">
          <path
            d="M1.5 1.5l6 6M7.5 1.5l-6 6"
            stroke="currentColor"
            strokeWidth="1.4"
            strokeLinecap="round"
          />
        </svg>
      </span>
      {/* mid-build underline shimmer */}
      {building && (
        <span
          aria-hidden
          className="animate-build-shimmer pointer-events-none absolute inset-x-2 bottom-0.5 h-0.5 rounded-full"
        />
      )}
    </button>
  );
}

/** A row inside a workspace popover (overflow or the off-editor chip): status dot
 *  + name + a close affordance. The focused row carries an accent tint so the chip
 *  menu shows which workspace you'd return to. */
function OverflowItem({
  path,
  name,
  status,
  focused = false,
  onFocus,
  onClose,
}: {
  path: string;
  name: string;
  status?: WorkspaceStatusKind;
  focused?: boolean;
  onFocus: (path: string) => void;
  onClose: (path: string) => void;
}) {
  return (
    <button
      type="button"
      title={name}
      aria-current={focused || undefined}
      onClick={() => onFocus(path)}
      onMouseDown={(e) => {
        if (e.button === 1) {
          e.preventDefault();
          onClose(path);
        }
      }}
      className={`group/row flex h-7.5 w-full items-center gap-2.25 rounded-md px-2.25 text-body transition-colors duration-100 ${
        focused ? "bg-accent-tint font-medium text-accent" : "text-ink hover:bg-surface-hover"
      }`}
    >
      <StatusDot status={status} focused={focused} />
      <span className="min-w-0 flex-1 truncate text-left">{name}</span>
      <span
        role="button"
        aria-label={`Close ${name}`}
        tabIndex={0}
        onClick={(e) => {
          e.stopPropagation();
          onClose(path);
        }}
        onMouseDown={(e) => e.stopPropagation()}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            e.stopPropagation();
            onClose(path);
          }
        }}
        className="grid h-4 w-4 place-items-center rounded text-ink-3 opacity-0 transition-opacity duration-100 hover:bg-line-2 hover:text-ink focus-visible:opacity-100 group-hover/row:opacity-100"
      >
        <svg width="9" height="9" viewBox="0 0 9 9" aria-hidden fill="none">
          <path
            d="M1.5 1.5l6 6M7.5 1.5l-6 6"
            stroke="currentColor"
            strokeWidth="1.4"
            strokeLinecap="round"
          />
        </svg>
      </span>
    </button>
  );
}

export default function WorkspaceSwitcher({
  openPaths,
  focusedPath,
  names,
  statuses,
  onFocus,
  onClose,
  onAdd,
}: WorkspaceSwitcherProps) {
  const [overflowOpen, setOverflowOpen] = useState(false);
  const overflowRef = useDismiss<HTMLDivElement>(overflowOpen, () => setOverflowOpen(false));

  const visible = openPaths.slice(0, MAX_VISIBLE);
  const collapsed = openPaths.slice(MAX_VISIBLE);

  // The overflow chip wears a dot when any collapsed tab is busy: amber wins
  // (any provisioning) > red (any error) so a mid-build hidden tab is loudest.
  const collapsedStatuses = collapsed.map((p) => statuses[p]);
  const chipDot: "amber" | "error" | null = collapsedStatuses.includes("provisioning")
    ? "amber"
    : collapsedStatuses.includes("error")
      ? "error"
      : null;

  const nameFor = (p: string) => names[p] ?? p;

  const close = (p: string) => {
    onClose(p);
    if (collapsed.length <= 1) setOverflowOpen(false);
  };

  return (
    <div className="flex items-center gap-2">
      <div className="flex items-center gap-0.5 rounded-[10px] border border-line bg-surface-2 p-0.75">
        {visible.map((path) => (
          <Pill
            key={path}
            path={path}
            name={nameFor(path)}
            status={statuses[path]}
            focused={path === focusedPath}
            onFocus={onFocus}
            onClose={onClose}
          />
        ))}

        {collapsed.length > 0 && (
          <div ref={overflowRef} className="relative">
            <button
              type="button"
              aria-haspopup="menu"
              aria-expanded={overflowOpen}
              title={`${collapsed.length} more`}
              onClick={() => setOverflowOpen((o) => !o)}
              className="flex h-6.5 items-center gap-1.25 rounded-md px-2.25 text-caption font-semibold text-ink-2 transition-colors duration-100 hover:bg-surface-hover"
            >
              {chipDot && (
                <span
                  aria-hidden
                  className={`h-1.75 w-1.75 shrink-0 rounded-full ${
                    chipDot === "amber" ? "bg-amber" : "bg-danger-bold"
                  }`}
                />
              )}
              <span>+{collapsed.length}</span>
              <ChevronDown size={12} strokeWidth={2.2} className="text-ink-3" aria-hidden />
            </button>

            {overflowOpen && (
              <div
                role="menu"
                className="absolute left-0 top-full z-50 mt-2 w-46.5 rounded-xl border border-line-2 bg-surface p-1.25 shadow-float"
              >
                {collapsed.map((path) => (
                  <OverflowItem
                    key={path}
                    path={path}
                    name={nameFor(path)}
                    status={statuses[path]}
                    onFocus={(p) => {
                      onFocus(p);
                      setOverflowOpen(false);
                    }}
                    onClose={close}
                  />
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      <button
        type="button"
        aria-label="Open a workspace"
        title="Open a workspace"
        onClick={onAdd}
        className="grid h-6.5 w-6.5 place-items-center rounded-lg border border-line text-ink-3 transition-colors duration-100 hover:bg-surface-2 hover:text-ink-2"
      >
        <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden fill="none">
          <path
            d="M7 2.5v9M2.5 7h9"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
          />
        </svg>
      </button>
    </div>
  );
}

/**
 * WorkspaceChip — the collapsed switcher shown on every surface that is NOT the
 * editor viewport (Home, the libraries, Settings, and workspace-scoped sub-pages).
 * A row of pills is per-workspace chrome with no business on a global page, so off
 * the editor it folds to one compact control: a summary status dot (amber if any
 * tab is building, red if any errored) + the open count, opening a menu that lists
 * every open workspace. That keeps ambient build status and one-click re-entry
 * without the pills crowding the page's own breadcrumb.
 */
function WorkspaceChip({
  openPaths,
  focusedPath,
  names,
  statuses,
  onFocus,
  onClose,
}: Omit<WorkspaceSwitcherProps, "onAdd">) {
  const [open, setOpen] = useState(false);
  const ref = useDismiss<HTMLDivElement>(open, () => setOpen(false));
  const nameFor = (p: string) => names[p] ?? p;

  // Aggregate busy state across all open tabs: amber (any building) beats red
  // (any error) so a mid-build workspace is the loudest signal; calm -> neutral.
  const all = openPaths.map((p) => statuses[p]);
  const summary: WorkspaceStatusKind | undefined =
    all.includes("provisioning") || all.includes("updating")
      ? "provisioning"
      : all.includes("error")
        ? "error"
        : undefined;

  const close = (p: string) => {
    onClose(p);
    if (openPaths.length <= 1) setOpen(false);
  };

  const label = `${openPaths.length} open ${openPaths.length === 1 ? "workspace" : "workspaces"}`;

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={label}
        title={label}
        onClick={() => setOpen((o) => !o)}
        className="flex h-8 items-center gap-1.75 rounded-lg border border-line-2 bg-surface pl-2.25 pr-2 text-body font-medium text-ink-2 transition-colors duration-150 hover:border-line-3 hover:text-ink"
      >
        <StatusDot status={summary} focused={false} />
        <span className="tabular-nums">{openPaths.length}</span>
        <ChevronDown size={13} strokeWidth={2.2} className="text-ink-3" aria-hidden />
      </button>

      {open && (
        <div
          role="menu"
          className="absolute left-0 top-full z-50 mt-2 w-52 rounded-xl border border-line-2 bg-surface p-1.25 shadow-float"
        >
          <div className="px-2.25 pb-1.25 pt-1 text-micro font-semibold uppercase tracking-eyebrow text-ink-3">
            Open workspaces
          </div>
          {/* Rendered in the order given: the bar hands us most-recently-viewed
              first (MRU), so the workspace you last had open sits on top. The pill
              bar keeps its stable left-to-right tab order instead. */}
          {openPaths.map((path) => (
            <OverflowItem
              key={path}
              path={path}
              name={nameFor(path)}
              status={statuses[path]}
              focused={path === focusedPath}
              onFocus={(p) => {
                onFocus(p);
                setOpen(false);
              }}
              onClose={close}
            />
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * WorkspaceSwitcherBar — the connected switcher. Wires the presentational
 * control to the session registry (open tabs + focus), per-tab engine statuses,
 * resolved display names, and router navigation.
 *
 * Picks its form by route: the full segmented tabs only on the editor viewport
 * (`/w/:wsPath`, the one route that publishes no crumb), the compact chip on every
 * other surface. Renders nothing when no tab is open (the launcher shows neither).
 */
export function WorkspaceSwitcherBar() {
  const { openPaths, recentPaths, focusedPath, close } = useWorkspaceSessions();
  const statuses = useWorkspaceStatuses();
  const navigate = useNavigate();
  // Exact match: `/w/:wsPath` is the editor index, while `/w/:wsPath/settings`
  // (etc.) are sub-pages that DO publish a crumb, so they get the chip too.
  const inEditor = useMatch("/w/:wsPath") != null;

  // Resolve display names from the registry; refresh when the tab set changes.
  // Fall back to the path's basename for any tab not yet in the registry.
  const [names, setNames] = useState<Record<string, string>>({});
  useEffect(() => {
    let live = true;
    listWorkspaces()
      .then((list) => {
        if (!live) return;
        const m: Record<string, string> = {};
        for (const w of list) m[w.path] = w.name;
        setNames(m);
      })
      .catch(() => {});
    return () => {
      live = false;
    };
    // Depend on the array reference, not its length: the registry hands back a
    // fresh array on any change (open/close AND a rename-refresh), so a rename
    // that keeps the same tab count still re-resolves the display name.
  }, [openPaths]);

  const nameFor = (p: string) => names[p] ?? p.split("/").pop() ?? "Workspace";
  const namesResolved = Object.fromEntries(openPaths.map((p) => [p, nameFor(p)]));

  const onFocus = (p: string) => navigate(editorPath(p));
  const onAdd = () => navigate("/");
  const onClose = (p: string) => {
    const wasFocused = p === focusedPath;
    const remaining = openPaths.filter((x) => x !== p);
    void closeWorkspaceTab(p); // kill its engine + reap its shell, backend-side
    close(p); // update the session registry (focuses last remaining)
    if (wasFocused) {
      const next = remaining[remaining.length - 1];
      navigate(next ? editorPath(next) : "/");
    }
  };

  if (openPaths.length === 0) return null;

  if (!inEditor) {
    // The chip menu is an MRU list, so it gets recentPaths (last-viewed first).
    return (
      <WorkspaceChip
        openPaths={recentPaths}
        focusedPath={focusedPath}
        names={namesResolved}
        statuses={statuses}
        onFocus={onFocus}
        onClose={onClose}
      />
    );
  }

  return (
    <WorkspaceSwitcher
      openPaths={openPaths}
      focusedPath={focusedPath}
      names={namesResolved}
      statuses={statuses}
      onFocus={onFocus}
      onClose={onClose}
      onAdd={onAdd}
    />
  );
}
