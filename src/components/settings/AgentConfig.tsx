/**
 * AgentConfig — the agent-config surface inside the Context settings section.
 * PER-WORKSPACE: which skills the coding agent uses + a narrow
 * runtime-settings set (auto-provision). There is no in-app agent launch — the
 * user runs their own agentic CLI in the terminal, which reads the workspace's
 * provisioned skill tree; so toggling a skill takes effect on the NEXT workspace
 * open (the provisioner re-runs and writes only the enabled skills).
 *
 * Loads the skills + config on mount (both per-active-workspace). Resolves to an
 * empty/idle state when no workspace is open (settings reachable from the
 * launcher), so this section simply shows a "open a workspace" hint there.
 */
import { useCallback, useEffect, useState } from "react";

import {
  listSkills,
  getAgentConfig,
  setAgentConfig,
  getAgentHarnessStatuses,
  refreshAgentSupport,
  type SkillInfo,
  type AgentConfig as AgentConfigData,
  type HarnessId,
  type HarnessStatus,
  type HarnessState,
} from "../../lib/ipc/config";

const HARNESSES: readonly { id: HarnessId; displayName: string }[] = [
  { id: "codex", displayName: "Codex" },
  { id: "claudeCode", displayName: "Claude Code" },
  { id: "openCode", displayName: "OpenCode" },
  { id: "geminiCli", displayName: "Gemini CLI" },
  { id: "copilotCli", displayName: "GitHub Copilot CLI" },
  { id: "pi", displayName: "Pi" },
];

const HARNESS_STATE_LABELS: Record<HarnessState, string> = {
  ready: "Ready",
  notInstalled: "Not installed",
  needsSetup: "Needs setup",
  unknown: "Unknown",
  unavailable: "Unavailable",
};

/**
 * A small accessible pill toggle — same graphite idiom as ViewportFeatures,
 * with a disabled (auto-provision off) state. Kept local so each settings
 * section is self-contained.
 */
function Toggle({
  checked,
  onChange,
  label,
  disabled = false,
}: {
  checked: boolean;
  onChange: () => void;
  label: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={onChange}
      className={`relative inline-flex h-5.5 w-9.5 shrink-0 items-center rounded-full outline-none transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-accent-tint disabled:cursor-not-allowed disabled:opacity-40 ${
        checked ? "bg-accent" : "bg-line-2"
      } ${!disabled && !checked ? "hover:bg-[rgba(18,20,28,.2)]" : ""}`}
    >
      <span
        className={`inline-block h-4 w-4 transform rounded-full bg-surface shadow-[0_1px_2px_rgba(16,18,24,.28)] transition-transform duration-150 ${
          checked ? "translate-x-4.75" : "translate-x-0.75"
        }`}
      />
    </button>
  );
}

export default function AgentConfig() {
  const [skills, setSkills] = useState<SkillInfo[] | null>(null); // null = loading
  const [config, setConfig] = useState<AgentConfigData | null>(null);
  const [statuses, setStatuses] = useState<HarnessStatus[] | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    Promise.all([listSkills(), getAgentConfig(), getAgentHarnessStatuses()]).then(([s, c, h]) => {
      if (cancelled) return;
      setSkills(s);
      setConfig(c);
      setStatuses(h);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  // Persist a new config: optimistic local update + backend write; revert + flag on error.
  const persist = useCallback(
    (next: AgentConfigData, nextSkills: SkillInfo[]) => {
      setError(null);
      const prevConfig = config;
      const prevSkills = skills;
      setConfig(next);
      setSkills(nextSkills);
      void setAgentConfig(next).catch((e) => {
        setConfig(prevConfig);
        setSkills(prevSkills);
        setError(e instanceof Error ? e.message : "Failed to save agent config");
      });
    },
    [config, skills],
  );

  const toggleSkill = useCallback(
    (name: string) => {
      if (!skills || !config) return;
      const nextSkills = skills.map((s) => (s.name === name ? { ...s, enabled: !s.enabled } : s));
      const enabledSkills = nextSkills.filter((s) => s.enabled).map((s) => s.name);
      persist({ ...config, enabledSkills }, nextSkills);
    },
    [skills, config, persist],
  );

  const toggleAutoProvision = useCallback(() => {
    if (!config || !skills) return;
    persist({ ...config, autoProvisionSkills: !config.autoProvisionSkills }, skills);
  }, [config, skills, persist]);

  const refreshSupport = useCallback(async () => {
    setError(null);
    setRefreshing(true);
    try {
      const result = await refreshAgentSupport();
      setStatuses(result.statuses);
      if (result.provisionReport.errors.length > 0)
        setError(result.provisionReport.errors.join("\n"));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to refresh agent support");
    } finally {
      setRefreshing(false);
    }
  }, []);

  // No workspace open (settings from the launcher): both calls returned empty/null.
  const noWorkspace = skills !== null && skills.length === 0 && config === null;
  const autoProvision = config?.autoProvisionSkills ?? true;

  return (
    <div className="mx-auto max-w-160 py-6.5">
      <section aria-labelledby="agent-support-heading">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 id="agent-support-heading" className="text-base font-bold tracking-snug text-ink">
              Agent support
            </h2>
            <p className="mt-1.25 text-body leading-normal text-ink-2">
              Readiness for the coding harnesses configured in this workspace.
            </p>
          </div>
          {!noWorkspace && statuses !== null && (
            <button
              type="button"
              disabled={refreshing}
              onClick={() => void refreshSupport()}
              className="shrink-0 rounded-lg border border-line bg-surface px-3 py-1.75 text-caption font-medium text-ink transition-colors hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-tint disabled:cursor-not-allowed disabled:opacity-50"
            >
              {refreshing ? "Refreshing agent support…" : "Refresh agent support"}
            </button>
          )}
        </div>

        {statuses === null ? (
          <div className="mt-4.5 text-body text-ink-3">Loading agent support…</div>
        ) : noWorkspace ? (
          <div className="mt-4.5 rounded-panel border border-dashed border-line-2 bg-surface-2 px-4 py-4.5 text-center text-body text-ink-3">
            Open a workspace to check agent support.
          </div>
        ) : (
          <HarnessRows statuses={statuses} />
        )}
      </section>

      {error && (
        <div className="mt-3 rounded-lg border border-danger-line bg-danger-bg px-3 py-2 font-mono text-caption text-danger">
          {error}
        </div>
      )}

      <section aria-labelledby="agent-skills-heading" className="mt-7">
        <h2 id="agent-skills-heading" className="text-base font-bold tracking-snug text-ink">
          Agent skills
        </h2>
        <p className="mt-1.25 text-body leading-normal text-ink-2">
          Which skills the coding agent uses in this workspace. Changes apply the next time you open
          it.
        </p>

        {skills === null ? (
          <div className="mt-4.5 text-body text-ink-3">Loading skills…</div>
        ) : noWorkspace ? (
          <div className="mt-4.5 rounded-panel border border-dashed border-line-2 bg-surface-2 px-4 py-4.5 text-center text-body text-ink-3">
            Open a workspace to configure its agent skills.
          </div>
        ) : (
          <>
            <label className="mt-4.5 flex cursor-pointer items-start gap-4 rounded-panel border border-line bg-surface px-4 py-3.5 transition-colors duration-150 hover:bg-surface-2">
              <div className="min-w-0 flex-1">
                <div className="text-body font-medium text-ink">Manage skills automatically</div>
                <div className="mt-0.5 text-xs leading-normal text-ink-3">
                  Write the enabled skills into the workspace on open. Turn off to hand-manage your
                  own skill files.
                </div>
              </div>
              <Toggle
                checked={autoProvision}
                label="Manage skills automatically"
                onChange={toggleAutoProvision}
              />
            </label>
            <div className="mt-3.5 divide-y divide-line overflow-hidden rounded-panel border border-line bg-surface">
              {skills.map((s) => (
                <label
                  key={s.name}
                  className={`flex items-start gap-4 px-4 py-3.5 transition-colors duration-150 ${
                    autoProvision ? "cursor-pointer hover:bg-surface-2" : "cursor-not-allowed"
                  }`}
                >
                  <div className="min-w-0 flex-1">
                    <div className="font-mono text-body font-medium text-ink">{s.name}</div>
                    <div className="mt-0.5 line-clamp-2 text-xs leading-normal text-ink-3">
                      {s.description}
                    </div>
                  </div>
                  <Toggle
                    checked={s.enabled}
                    label={s.name}
                    disabled={!autoProvision}
                    onChange={() => toggleSkill(s.name)}
                  />
                </label>
              ))}
            </div>
          </>
        )}
      </section>
    </div>
  );
}

function HarnessRows({ statuses }: { statuses: HarnessStatus[] }) {
  const byId = new Map(statuses.map((status) => [status.id, status]));
  return (
    <div className="mt-4.5 divide-y divide-line overflow-hidden rounded-panel border border-line bg-surface">
      {HARNESSES.map((harness) => {
        const status = byId.get(harness.id);
        const state = status?.state ?? "unknown";
        const showPiRemediation =
          harness.id === "pi" && state === "needsSetup" && typeof status?.remediation === "string";
        return (
          <div key={harness.id} className="flex items-start gap-4 px-4 py-3.5">
            <div className="min-w-0 flex-1">
              <div className="text-body font-medium text-ink">{harness.displayName}</div>
              {showPiRemediation && (
                <code className="mt-1 block w-fit select-all rounded bg-surface-2 px-2 py-1 font-mono text-caption text-ink-2">
                  {status.remediation}
                </code>
              )}
              {status && status.userOwnedPaths.length > 0 && (
                <div className="mt-1 text-caption text-ink-3">
                  User-owned: {status.userOwnedPaths.join(", ")}
                </div>
              )}
            </div>
            <span className="rounded-full bg-surface-2 px-2 py-0.5 text-micro text-ink-3">
              {HARNESS_STATE_LABELS[state]}
            </span>
          </div>
        );
      })}
    </div>
  );
}
