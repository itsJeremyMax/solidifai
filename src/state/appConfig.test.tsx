// @vitest-environment jsdom
// DOM test: the AppConfigProvider's optimistic-then-revert behavior. This is the
// key regression to lock: a toggle must flip instantly, then snap back (and
// surface an error) if the backend write fails.
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";

import { AppConfigProvider, useAppConfig } from "./appConfig";

// Mock the ipc boundary so no real Tauri command runs. getAppConfig resolves a
// known config; setAppConfig is wired per-test to resolve or reject.
vi.mock("../lib/ipc/config", async () => {
  const actual = await vi.importActual<typeof import("../lib/ipc/config")>("../lib/ipc/config");
  return {
    ...actual, // keep DEFAULT_APP_CONFIG + the AppConfig type re-export
    getAppConfig: vi.fn(),
    setAppConfig: vi.fn(),
  };
});

import { getAppConfig, setAppConfig, DEFAULT_APP_CONFIG } from "../lib/ipc/config";

const getAppConfigMock = vi.mocked(getAppConfig);
const setAppConfigMock = vi.mocked(setAppConfig);

// Tiny consumer: shows the gtao flag + error, and flips gtao on click.
function Probe() {
  const { config, error, loading } = useAppConfig();
  const { setFlag } = useAppConfig();
  return (
    <div>
      <span data-testid="loading">{String(loading)}</span>
      <span data-testid="gtao">{String(config.gtao)}</span>
      <span data-testid="error">{error ?? "none"}</span>
      <button onClick={() => setFlag("gtao", !config.gtao)}>toggle</button>
    </div>
  );
}

function renderProvider() {
  return render(
    <AppConfigProvider>
      <Probe />
    </AppConfigProvider>,
  );
}

describe("AppConfigProvider", () => {
  beforeEach(() => {
    // Known starting config: gtao on.
    getAppConfigMock.mockResolvedValue({ ...DEFAULT_APP_CONFIG, gtao: true });
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("loads the initial config from the backend", async () => {
    renderProvider();
    await waitFor(() => expect(screen.getByTestId("loading").textContent).toBe("false"));
    expect(screen.getByTestId("gtao").textContent).toBe("true");
  });

  it("flips optimistically then reverts and surfaces an error when persist fails", async () => {
    // The persist rejects, so the optimistic flip must roll back.
    setAppConfigMock.mockRejectedValue(new Error("disk full"));
    renderProvider();
    await waitFor(() => expect(screen.getByTestId("loading").textContent).toBe("false"));
    expect(screen.getByTestId("gtao").textContent).toBe("true");

    fireEvent.click(screen.getByText("toggle"));

    // Optimistic flip is synchronous with the click (true -> false).
    expect(screen.getByTestId("gtao").textContent).toBe("false");

    // After the rejected write settles, the value reverts and the error appears.
    await waitFor(() => {
      expect(screen.getByTestId("gtao").textContent).toBe("true");
      expect(screen.getByTestId("error").textContent).toBe("disk full");
    });
    expect(setAppConfigMock).toHaveBeenCalledWith({ gtao: false });
  });

  it("adopts the backend's merged result on a successful persist", async () => {
    // Backend echoes the flip as authoritative truth.
    setAppConfigMock.mockResolvedValue({ ...DEFAULT_APP_CONFIG, gtao: false });
    renderProvider();
    await waitFor(() => expect(screen.getByTestId("loading").textContent).toBe("false"));

    fireEvent.click(screen.getByText("toggle"));
    expect(screen.getByTestId("gtao").textContent).toBe("false");

    await waitFor(() => {
      expect(screen.getByTestId("gtao").textContent).toBe("false");
      expect(screen.getByTestId("error").textContent).toBe("none");
    });
  });
});
