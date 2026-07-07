import { useCallback, useState } from "react";
import { BookOpen, Bug, CircleHelp, Info } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { useDismiss } from "../hooks/useDismiss";
import { MENU_PANEL } from "../lib/styles";

/** Shared lucide stroke weight to match the design language. */
const ICON_STROKE = 1.7;

/** One row of the help menu: an icon, a label, and a destination. */
function MenuItem({
  icon,
  label,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      role="menuitem"
      onClick={onClick}
      className="flex w-full items-center gap-2.25 rounded-lg px-2.5 py-2 text-left text-body text-ink transition-colors duration-150 hover:bg-surface-2 focus-visible:bg-surface-2 focus-visible:outline-none"
    >
      <span className="text-ink-3">{icon}</span>
      {label}
    </button>
  );
}

/**
 * HelpMenu — the "?" header control and its dropdown (Documentation, Report a
 * problem, About). It navigates to app-global routes itself, so it drops into any
 * header surface (home + editor) with only its trigger styling passed in. Closes
 * on outside-click or Escape via useDismiss. The trigger's container must not clip
 * overflow, or the dropdown will be cut off.
 */
export default function HelpMenu({ triggerClassName }: { triggerClassName: string }) {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const ref = useDismiss<HTMLDivElement>(
    open,
    useCallback(() => setOpen(false), []),
  );

  function go(path: string) {
    setOpen(false);
    navigate(path);
  }

  return (
    <div ref={ref} className="relative flex">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Help"
        title="Help"
        className={triggerClassName}
      >
        <CircleHelp size={16} strokeWidth={ICON_STROKE} />
      </button>

      {open && (
        <div role="menu" className={`${MENU_PANEL} right-0 top-full mt-2 w-52`}>
          <MenuItem
            icon={<BookOpen size={15} strokeWidth={ICON_STROKE} />}
            label="Documentation"
            onClick={() => go("/docs")}
          />
          <MenuItem
            icon={<Bug size={15} strokeWidth={ICON_STROKE} />}
            label="Report a problem"
            onClick={() => go("/help")}
          />
          <MenuItem
            icon={<Info size={15} strokeWidth={ICON_STROKE} />}
            label="About solidifai"
            onClick={() => go("/settings/about")}
          />
        </div>
      )}
    </div>
  );
}
