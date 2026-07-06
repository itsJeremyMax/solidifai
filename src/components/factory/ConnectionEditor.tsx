/**
 * ConnectionEditor — add / edit a connection, as a nested route (`factory/new`,
 * `factory/:connectionId`) rendered over the grid. A centered modal (backdrop +
 * Escape close via useDismiss). Saves persist the whole connection list back
 * through the grid's Outlet context.
 */
import { useEffect, useState } from "react";
import { Printer, Trash2, X } from "lucide-react";
import { useNavigate, useOutletContext, useParams } from "react-router-dom";

import type { Destination, ProfileSet } from "../../lib/fabrication";
import Select from "../ui/Select";
import { useDismiss } from "../../hooks/useDismiss";
import { useGoBack } from "../../hooks/useGoBack";
import { ACCENT_CTA } from "../../lib/styles";
import type { FactoryOutletContext } from "./factoryContext";

const ICON_STROKE = 1.7;
const PROVIDERS = [{ value: "orca", label: "OrcaSlicer" }];
const ENGINE_HALO = "0 0 0 4px rgba(25,169,87,.14)";

function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <span className="mb-1.5 block text-micro font-bold uppercase tracking-eyebrow text-ink-3">
      {children}
    </span>
  );
}

/**
 * Slicer detection note: tells the user whether OrcaSlicer was found (and where
 * the profile dropdowns are sourced from), or links to Settings → Slicers to set
 * the binary path. Reads the native `get_slicer_profiles` result, so it works on
 * the Factory page with no workspace engine.
 */
function SlicerStatus({ profiles, onSetup }: { profiles: ProfileSet | null; onSetup: () => void }) {
  let tone: "ok" | "off" | "wait" = "wait";
  let title = "Checking for a slicer...";
  let body: React.ReactNode = null;

  if (profiles?.found) {
    tone = "ok";
    title = `OrcaSlicer${profiles.version ? ` ${profiles.version}` : ""} detected`;
    body =
      profiles.printers.length + profiles.filaments.length > 0
        ? "Printer and filament profiles loaded from your local install."
        : "No saved printer or filament profiles yet.";
  } else if (profiles) {
    tone = "off";
    title = "OrcaSlicer not detected";
    body = (
      <>
        Install it, or{" "}
        <button
          type="button"
          onClick={onSetup}
          className="font-medium text-accent transition-colors duration-150 hover:text-accent-press"
        >
          set the binary path
        </button>{" "}
        to load profiles.
      </>
    );
  }

  const dot =
    tone === "ok" ? "bg-engine" : tone === "off" ? "bg-ink-3" : "bg-amber animate-engine-pulse";

  return (
    <div className="mb-3.5 flex items-start gap-2.5 rounded-[11px] border border-line bg-surface-2 px-3.25 py-2.5">
      <span
        className={`mt-1 h-2 w-2 shrink-0 rounded-full ${dot}`}
        style={tone === "ok" ? { boxShadow: ENGINE_HALO } : undefined}
      />
      <div className="min-w-0 text-caption leading-relaxed">
        <div className="font-medium text-ink">{title}</div>
        {body && <div className="text-ink-3">{body}</div>}
      </div>
    </div>
  );
}

export default function ConnectionEditor() {
  const navigate = useNavigate();
  const { connectionId } = useParams();
  const ctx = useOutletContext<FactoryOutletContext>();

  const isNew = connectionId === undefined;
  const existing = isNew ? null : (ctx.destinations.find((d) => d.id === connectionId) ?? null);
  const close = useGoBack("..", { replace: true });
  const ref = useDismiss<HTMLDivElement>(true, close);

  // Stale deep link: editing an id that no longer exists.
  useEffect(() => {
    if (!isNew && !existing) navigate("..", { replace: true });
  }, [isNew, existing, navigate]);

  // Profiles power the printer/filament selects; load them once if absent.
  useEffect(() => {
    if (!ctx.profiles) void ctx.fetchProfiles();
  }, [ctx]);

  const [name, setName] = useState(existing?.name ?? "");
  const [provider, setProvider] = useState(existing?.provider ?? "orca");
  const [printer, setPrinter] = useState(existing?.printerProfile ?? "");
  const [filament, setFilament] = useState(existing?.filamentProfile ?? "");
  const [process, setProcess] = useState(existing?.processProfile ?? "");
  const [confirmingRemove, setConfirmingRemove] = useState(false);

  const printerOpts = [
    { value: "", label: "Default" },
    ...(ctx.profiles?.printers ?? []).map((p) => ({ value: p, label: p })),
  ];
  const filamentOpts = [
    { value: "", label: "Default" },
    ...(ctx.profiles?.filaments ?? []).map((f) => ({ value: f, label: f })),
  ];
  const processOpts = [
    { value: "", label: "Default" },
    ...(ctx.profiles?.processes ?? []).map((p) => ({ value: p, label: p })),
  ];
  // Nothing to pick beyond "Default" until profiles load from a detected slicer,
  // so the dropdowns are disabled in that state rather than offering a lone option.
  const profilesLoaded = ctx.profiles != null;
  const printerDisabled = profilesLoaded && printerOpts.length <= 1;
  const filamentDisabled = profilesLoaded && filamentOpts.length <= 1;
  const processDisabled = profilesLoaded && processOpts.length <= 1;

  // Connections are identified by name in the Make-tab picker, so duplicate names
  // are ambiguous. Same provider/profiles under different names is fine (two
  // physical printers sharing a profile), so we only guard the name.
  const trimmedName = name.trim();
  const nameTaken = ctx.destinations.some(
    (d) => d.id !== existing?.id && d.name.trim().toLowerCase() === trimmedName.toLowerCase(),
  );
  const canSave = trimmedName.length > 0 && !nameTaken;

  const submit = () => {
    if (!canSave) return;
    const dest: Destination = {
      id: isNew ? crypto.randomUUID() : existing!.id,
      name: name.trim(),
      kind: existing?.kind ?? "local",
      provider,
      printerProfile: printer || undefined,
      filamentProfile: filament || undefined,
      processProfile: process || undefined,
      connection: existing?.connection,
    };
    const next = isNew
      ? [...ctx.destinations, dest]
      : ctx.destinations.map((d) => (d.id === dest.id ? dest : d));
    void ctx.save(next);
    close();
  };

  const remove = () => {
    if (isNew || !existing) return;
    void ctx.save(ctx.destinations.filter((d) => d.id !== existing.id));
    close();
  };

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-[rgba(18,20,28,.34)] px-5 backdrop-blur-xs">
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-labelledby="printer-editor-title"
        className="animate-rise w-full max-w-110 rounded-panel border border-line-2 bg-surface p-5 shadow-float"
      >
        {confirmingRemove && existing ? (
          <RemoveConfirm
            name={existing.name}
            onCancel={() => setConfirmingRemove(false)}
            onConfirm={remove}
          />
        ) : (
          <>
            <div className="mb-3.5 flex items-center gap-2.5">
              <span className="grid h-8.5 w-8.5 shrink-0 place-items-center rounded-xl border border-line-2 bg-surface-2 text-accent">
                <Printer size={17} strokeWidth={ICON_STROKE} />
              </span>
              <h2 id="printer-editor-title" className="text-base font-bold tracking-snug text-ink">
                {isNew ? "New connection" : "Edit connection"}
              </h2>
              <div className="flex-1" />
              <button
                type="button"
                onClick={close}
                aria-label="Close"
                className="grid h-7 w-7 place-items-center rounded-lg text-ink-3 transition-colors duration-150 hover:bg-surface-2 hover:text-ink"
              >
                <X size={16} strokeWidth={ICON_STROKE} />
              </button>
            </div>

            <label className="mb-3.5 block">
              <FieldLabel>Name</FieldLabel>
              <input
                type="text"
                value={name}
                autoFocus
                spellCheck={false}
                placeholder="Garage printer"
                aria-invalid={nameTaken}
                onChange={(e) => setName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && canSave) submit();
                }}
                className={`h-9.5 w-full rounded-lg border bg-surface-2 px-3 text-sm text-ink outline-none transition-colors duration-150 placeholder:text-ink-3 focus:bg-surface focus:ring-2 ${
                  nameTaken
                    ? "border-danger-line focus:border-danger focus:ring-danger-bg"
                    : "border-line-2 focus:border-accent focus:ring-accent-tint"
                }`}
              />
              {nameTaken && (
                <span className="mt-1.5 block text-caption text-danger">
                  A connection named &ldquo;{trimmedName}&rdquo; already exists.
                </span>
              )}
            </label>

            <div className="mb-3.5">
              <FieldLabel>Provider</FieldLabel>
              <Select
                value={provider}
                onChange={setProvider}
                ariaLabel="Provider"
                options={PROVIDERS}
              />
            </div>

            <SlicerStatus
              profiles={ctx.profiles}
              onSetup={() => navigate("../../settings/slicers")}
            />

            <div className="mb-3.5">
              <FieldLabel>Printer profile</FieldLabel>
              <Select
                value={printer}
                onChange={setPrinter}
                ariaLabel="Printer profile"
                options={printerOpts}
                disabled={printerDisabled}
              />
            </div>

            <div className="mb-3.5">
              <FieldLabel>Filament profile</FieldLabel>
              <Select
                value={filament}
                onChange={setFilament}
                ariaLabel="Filament profile"
                options={filamentOpts}
                disabled={filamentDisabled}
              />
            </div>

            <div className="mb-4.5">
              <FieldLabel>Process profile</FieldLabel>
              <Select
                value={process}
                onChange={setProcess}
                ariaLabel="Process profile"
                options={processOpts}
                disabled={processDisabled}
              />
            </div>

            <div className="flex items-center justify-between gap-2.25">
              {existing ? (
                <button
                  type="button"
                  onClick={() => setConfirmingRemove(true)}
                  className="inline-flex h-9 items-center gap-1.75 rounded-lg px-3 text-body font-medium text-danger transition-colors duration-150 hover:bg-danger-bg"
                >
                  <Trash2 size={15} strokeWidth={ICON_STROKE} />
                  Remove
                </button>
              ) : (
                <span />
              )}
              <div className="flex items-center gap-2.25">
                <button
                  type="button"
                  onClick={close}
                  className="inline-flex h-9 items-center rounded-lg px-3.5 text-body font-medium text-ink-2 transition-colors duration-150 hover:bg-surface-2 hover:text-ink"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={submit}
                  disabled={!canSave}
                  className={`${ACCENT_CTA} h-9 px-4 disabled:opacity-45 disabled:hover:bg-accent`}
                >
                  {isNew ? "Add connection" : "Save"}
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

/** The destructive confirm step shown in place of the form before a remove. */
function RemoveConfirm({
  name,
  onCancel,
  onConfirm,
}: {
  name: string;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <>
      <div className="mb-3.5 flex items-center gap-2.5">
        <span className="grid h-8.5 w-8.5 shrink-0 place-items-center rounded-xl border border-danger-line bg-danger-bg text-danger">
          <Trash2 size={17} strokeWidth={ICON_STROKE} />
        </span>
        <h2 id="printer-editor-title" className="text-base font-bold tracking-snug text-ink">
          Remove connection
        </h2>
      </div>

      <p className="mb-4.5 text-body leading-normal text-ink-2">
        Remove <span className="font-semibold text-ink">{name}</span> from your connections? This
        cannot be undone.
      </p>

      <div className="flex items-center justify-end gap-2.25">
        <button
          type="button"
          onClick={onCancel}
          className="inline-flex h-9 items-center rounded-lg px-3.5 text-body font-medium text-ink-2 transition-colors duration-150 hover:bg-surface-2 hover:text-ink"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={onConfirm}
          className="inline-flex h-9 items-center gap-1.75 rounded-lg border border-transparent bg-danger px-4 text-body font-medium text-white shadow-[0_1px_1px_rgba(160,30,34,.4),inset_0_1px_0_rgba(255,255,255,.2)] transition-colors duration-150 hover:bg-danger-press"
        >
          <Trash2 size={14} strokeWidth={ICON_STROKE} />
          Remove
        </button>
      </div>
    </>
  );
}
