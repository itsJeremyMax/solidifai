import { Box } from "lucide-react";

interface WorkspaceThumbProps {
  name: string;
  src: string | null;
  className?: string;
}

/**
 * Render tile for a workspace — shows captured PNG or a calm studio-sweep
 * placeholder with a muted Box glyph. Presentational; no state or effects.
 * Callers control sizing via className.
 */
export function WorkspaceThumb({ name, src, className = "" }: WorkspaceThumbProps) {
  return (
    <div
      className={`relative overflow-hidden border-b border-line ${className}`}
      style={{
        background: "radial-gradient(120% 100% at 50% 0%, #ffffff 0%, #f1f1ee 58%, #e7e7e3 100%)",
      }}
    >
      {src ? (
        <img
          src={src}
          alt={`${name} render`}
          className="h-full w-full object-cover"
          loading="lazy"
        />
      ) : (
        <div
          data-testid="thumb-placeholder"
          className="flex h-full w-full flex-col items-center justify-center"
        >
          {/* Muted cube glyph — low-contrast, intentional "no render yet" state */}
          <Box size={28} strokeWidth={1.5} className="text-ink-3 opacity-40" aria-hidden />
          {/* Contact-shadow ellipse echoing the mockup's ::after pseudo-element */}
          <div
            aria-hidden
            className="absolute"
            style={{
              bottom: "18%",
              left: "50%",
              transform: "translateX(-50%)",
              width: "46%",
              height: "9%",
              borderRadius: "50%",
              background: "radial-gradient(ellipse, rgba(20,22,30,0.16), transparent 70%)",
              filter: "blur(2px)",
            }}
          />
        </div>
      )}
    </div>
  );
}
