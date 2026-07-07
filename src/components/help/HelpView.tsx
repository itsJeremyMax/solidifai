/**
 * HelpView — the `/help` page: a short form that opens a prefilled GitHub issue.
 *
 * The heavy lifting (which form to target, how fields map, what gets attached)
 * lives in lib/help.ts; this component only gathers the category/title/details,
 * shows the system info that will ride along (opt-out), and hands off to the
 * browser. A docs link sits up top because many questions are already answered
 * there. Filing needs a GitHub account, which we say plainly near the button.
 */
import { useEffect, useState } from "react";
import { ArrowLeft, ArrowRight, BookOpen, ExternalLink } from "lucide-react";
import { Link } from "react-router-dom";
import { openUrl } from "@tauri-apps/plugin-opener";

import Select from "../ui/Select";
import { buildIssueUrl, HELP_CATEGORIES, type HelpCategory } from "../../lib/help";
import { buildDiagnostics, loadAppInfo, type AppInfo } from "../../lib/appInfo";
import { useGoBack } from "../../hooks/useGoBack";
import { useHeaderSlot } from "../../state/headerSlot";
import { ACCENT_CTA } from "../../lib/styles";

const ICON_STROKE = 1.7;

/** Height-agnostic field recipe (shared by the title input and the textarea). */
const FIELD =
  "w-full rounded-lg border border-line-2 bg-surface-2 px-3 text-sm text-ink outline-none transition-colors duration-150 placeholder:text-ink-3 focus:border-accent focus:bg-surface focus:ring-2 focus:ring-accent-tint";

function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <span className="mb-1.5 block text-micro font-bold uppercase tracking-eyebrow text-ink-3">
      {children}
    </span>
  );
}

export default function HelpView() {
  const goBack = useGoBack("/");

  useHeaderSlot({
    crumb: (
      <div className="flex items-center gap-3.5">
        <button
          type="button"
          onClick={goBack}
          className="inline-flex h-8 items-center gap-1.75 rounded-lg border border-line-2 bg-surface pl-2 pr-3 text-body font-medium text-ink transition-colors duration-150 hover:border-line-3"
        >
          <ArrowLeft className="opacity-70" size={16} strokeWidth={ICON_STROKE} />
          Back
        </button>
        <div className="flex items-center gap-2 text-body text-ink-3">
          <span className="opacity-50">/</span>
          <span className="font-medium text-ink-2">Help</span>
        </div>
      </div>
    ),
  });

  const [info, setInfo] = useState<AppInfo | null>(null); // null = loading
  const [category, setCategory] = useState<HelpCategory>("bug");
  const [title, setTitle] = useState("");
  const [details, setDetails] = useState("");
  const [includeDiag, setIncludeDiag] = useState(true);

  useEffect(() => {
    let cancelled = false;
    loadAppInfo().then((i) => {
      if (!cancelled) setInfo(i);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const def = HELP_CATEGORIES.find((c) => c.value === category) ?? HELP_CATEGORIES[0];
  const diagnostics = info ? buildDiagnostics(info) : "";
  const canSubmit = title.trim() !== "" || details.trim() !== "";

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    const url = buildIssueUrl({
      category,
      title,
      details,
      version: info?.version ?? "",
      os: info?.os ?? "",
      diagnostics,
      includeDiagnostics: includeDiag,
    });
    // Best-effort: a blocked opener must not surface as a crash.
    void openUrl(url).catch(() => {});
  }

  return (
    <div className="flex min-h-0 w-full flex-1 flex-col overflow-y-auto bg-surface">
      <div className="mx-auto w-full max-w-160 px-6 py-6.5">
        <h1 className="text-xl font-bold tracking-snug text-ink">Report a problem</h1>
        <p className="mt-1 text-body leading-relaxed text-ink-2">
          Found a bug, have an idea, or just stuck? Send it our way. This opens a prefilled issue on
          GitHub, where you can review it before posting.
        </p>

        {/* Docs first — many questions are already answered there. */}
        <Link
          to="/docs"
          className="group mt-5 flex items-center gap-3 rounded-panel border border-line bg-surface-2 px-4 py-3.5 transition-colors duration-150 hover:border-line-3"
        >
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-line-2 bg-surface text-ink-2">
            <BookOpen size={17} strokeWidth={ICON_STROKE} />
          </span>
          <span className="min-w-0">
            <span className="block text-body font-medium text-ink">
              Check the documentation first
            </span>
            <span className="block text-caption text-ink-3">
              Many questions are already answered in the guides.
            </span>
          </span>
          <ArrowRight
            className="ml-auto shrink-0 text-ink-3 transition-transform duration-150 group-hover:translate-x-0.5"
            size={16}
            strokeWidth={ICON_STROKE}
          />
        </Link>

        <form onSubmit={handleSubmit} className="mt-6 flex flex-col gap-4">
          <div>
            <FieldLabel>Category</FieldLabel>
            <Select
              value={category}
              onChange={(v) => setCategory(v as HelpCategory)}
              options={HELP_CATEGORIES.map((c) => ({ value: c.value, label: c.label }))}
              ariaLabel="Category"
            />
          </div>

          <div>
            <FieldLabel>Title</FieldLabel>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="A short summary"
              className={`${FIELD} h-9.5`}
            />
          </div>

          <div>
            <FieldLabel>{def.detailLabel}</FieldLabel>
            <textarea
              value={details}
              onChange={(e) => setDetails(e.target.value)}
              placeholder={def.detailPlaceholder}
              rows={6}
              className={`${FIELD} min-h-32 resize-y py-2.5 leading-normal`}
            />
          </div>

          {/* System info — shown so it's never a surprise, opt-out with the checkbox. */}
          <div className="rounded-panel border border-line bg-surface-2 p-3.5">
            <label className="flex cursor-pointer select-none items-center gap-2.5">
              <input
                type="checkbox"
                checked={includeDiag}
                onChange={(e) => setIncludeDiag(e.target.checked)}
                className="h-4 w-4 rounded border-line-2 accent-accent"
              />
              <span className="text-body font-medium text-ink">Attach system info</span>
              <span className="text-caption text-ink-3">Helps us reproduce the issue</span>
            </label>
            <pre
              className={`mt-3 overflow-x-auto rounded-lg border border-line bg-surface px-3 py-2.5 font-mono text-caption leading-relaxed text-ink-2 transition-opacity duration-150 ${
                includeDiag ? "" : "opacity-40"
              }`}
            >
              {info === null ? "Loading system info…" : diagnostics}
            </pre>
          </div>

          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1.5">
            <button
              type="submit"
              disabled={!canSubmit}
              className={`${ACCENT_CTA} h-9 px-3.5 disabled:opacity-40`}
            >
              <ExternalLink size={15} strokeWidth={2} />
              Open on GitHub
            </button>
            <span className="text-caption text-ink-3">
              Opens in your browser. A GitHub account is needed to post.
            </span>
          </div>
        </form>
      </div>
    </div>
  );
}
