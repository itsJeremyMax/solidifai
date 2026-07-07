/**
 * Reveal — animates its children in on mount with a soft rise + fade, using only
 * Tailwind transition utilities (no global keyframes). Used by the update popover
 * and the companion toast so both share the same entrance. Respects reduced motion.
 */
import { useEffect, useState, type ReactNode } from "react";

export default function Reveal({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  const [entered, setEntered] = useState(false);
  useEffect(() => {
    const raf = requestAnimationFrame(() => setEntered(true));
    return () => cancelAnimationFrame(raf);
  }, []);
  return (
    <div
      className={`transition duration-300 ease-out-soft motion-reduce:transition-none ${
        entered ? "translate-y-0 opacity-100" : "translate-y-2 opacity-0"
      } ${className}`}
    >
      {children}
    </div>
  );
}
