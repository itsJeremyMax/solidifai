// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const { invoke } = vi.hoisted(() => ({ invoke: vi.fn() }));

vi.mock("../../lib/ipc/core", () => ({ invoke }));

import {
  getAgentHarnessStatuses,
  refreshAgentSupport,
  type HarnessStatus,
} from "../../lib/ipc/config";
import AgentConfig from "./AgentConfig";

const STATUS_NAMES = ["Codex", "Claude Code", "OpenCode", "Gemini CLI", "GitHub Copilot CLI", "Pi"];

const initialStatuses: HarnessStatus[] = [
  { id: "codex", displayName: "Codex", state: "ready", remediation: null, userOwnedPaths: [] },
  {
    id: "claudeCode",
    displayName: "Claude Code",
    state: "notInstalled",
    remediation: null,
    userOwnedPaths: [],
  },
  {
    id: "openCode",
    displayName: "OpenCode",
    state: "ready",
    remediation: null,
    userOwnedPaths: [],
  },
  {
    id: "geminiCli",
    displayName: "Gemini CLI",
    state: "ready",
    remediation: null,
    userOwnedPaths: [],
  },
  {
    id: "copilotCli",
    displayName: "GitHub Copilot CLI",
    state: "notInstalled",
    remediation: null,
    userOwnedPaths: [],
  },
  { id: "pi", displayName: "Pi", state: "ready", remediation: null, userOwnedPaths: [] },
];

const refreshedStatuses: HarnessStatus[] = initialStatuses.map((status) =>
  status.id === "pi"
    ? { ...status, state: "needsSetup", remediation: "pi install npm:pi-mcp-extension" }
    : status,
);

function defaultResponse(command: string) {
  switch (command) {
    case "list_skills":
      return [{ name: "using-solidifai", description: "Use the CAD workspace", enabled: true }];
    case "get_agent_config":
      return { enabledSkills: null, autoProvisionSkills: true };
    case "get_agent_harness_statuses":
      return initialStatuses;
    default:
      throw new Error(`Unexpected command: ${command}`);
  }
}

describe("AgentConfig", () => {
  beforeEach(() => {
    invoke.mockImplementation(async (command: string) => defaultResponse(command));
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders the six deterministic harness rows and only shows Pi remediation after setup is needed", async () => {
    render(<AgentConfig />);

    expect(await screen.findByRole("heading", { name: "Agent support" })).toBeTruthy();
    const names = STATUS_NAMES.map((name) => screen.getByText(name));
    for (const name of names) expect(name).toBeTruthy();
    const statusPanel = names[0].parentElement?.parentElement?.parentElement;
    expect(statusPanel).toBeTruthy();
    expect(Array.from(statusPanel?.children ?? []).map((row) => row.textContent)).toEqual([
      "CodexReady",
      "Claude CodeNot installed",
      "OpenCodeReady",
      "Gemini CLIReady",
      "GitHub Copilot CLINot installed",
      "PiReady",
    ]);
    expect(screen.queryByText("pi install npm:pi-mcp-extension")).toBeNull();
  });

  it("refreshes readiness statuses without erasing existing skill controls", async () => {
    invoke.mockImplementation(async (command: string) => {
      if (command === "refresh_agent_support") {
        return {
          provisionReport: { written: [], skippedUserOwned: [], errors: [] },
          statuses: refreshedStatuses,
        };
      }
      return defaultResponse(command);
    });
    render(<AgentConfig />);

    await screen.findByText("using-solidifai");
    fireEvent.click(screen.getByRole("button", { name: "Refresh agent support" }));

    await waitFor(() => expect(invoke).toHaveBeenCalledWith("refresh_agent_support"));
    expect(await screen.findByText("pi install npm:pi-mcp-extension")).toBeTruthy();
    expect(screen.getByRole("switch", { name: "using-solidifai" })).toBeTruthy();
  });

  it("surfaces a refresh error without erasing existing skill controls", async () => {
    invoke.mockImplementation(async (command: string) => {
      if (command === "refresh_agent_support") throw new Error("workspace unavailable");
      return defaultResponse(command);
    });
    render(<AgentConfig />);

    await screen.findByText("using-solidifai");
    fireEvent.click(screen.getByRole("button", { name: "Refresh agent support" }));

    expect(await screen.findByText("workspace unavailable")).toBeTruthy();
    expect(screen.getByRole("switch", { name: "using-solidifai" })).toBeTruthy();
  });

  it("uses a safe read wrapper and a mutating wrapper that rethrows backend failures", async () => {
    invoke.mockRejectedValueOnce(new Error("unavailable"));
    await expect(getAgentHarnessStatuses()).resolves.toEqual([]);

    invoke.mockRejectedValueOnce(new Error("workspace unavailable"));
    await expect(refreshAgentSupport()).rejects.toThrow("workspace unavailable");
  });
});
