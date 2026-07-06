/**
 * Spinner — lucide `Loader2` with the spin animation, at the design's stroke
 * weight. Shared by buttons across the launcher, settings, and dialogs so the
 * in-flight indicator looks identical everywhere.
 *
 * The default `size` (15) matches the inline-button glyph size; callers that
 * need a different size (e.g. the workspace-card chevron slot) pass `size`
 * explicitly.
 */
import { Loader2 } from "lucide-react";

export default function Spinner({
  className = "",
  size = 15,
}: {
  className?: string;
  size?: number;
}) {
  return <Loader2 className={`animate-spin ${className}`} size={size} strokeWidth={2.2} />;
}
