// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import type { SectionState } from "../../state/useInspectorPrefs";

const mocks = vi.hoisted(() => ({
  requirements: vi.fn(),
  dfm: vi.fn(),
  stress: vi.fn(),
}));

vi.mock("../../hooks/useRequirements", () => ({ useRequirements: mocks.requirements }));
vi.mock("../../hooks/useDfm", () => ({ useDfm: mocks.dfm }));
vi.mock("../../hooks/useStress", () => ({ useStress: mocks.stress }));
vi.mock("./CollapsibleSection", () => ({
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
vi.mock("./GoalsSection", () => ({ default: () => null }));
vi.mock("./DfmSection", () => ({ default: () => null }));
vi.mock("./StressSection", () => ({ default: () => null }));
vi.mock("./FitCheckSection", () => ({ default: () => null }));

import ChecksPanel from "./ChecksPanel";

afterEach(cleanup);

describe("ChecksPanel", () => {
  it("does not show a clean verdict while replacing reports for a new build", () => {
    mocks.requirements.mockReturnValue({
      report: { requirements: [], summary: { allMet: true } },
      loading: true,
    });
    mocks.dfm.mockReturnValue({
      report: { summary: { critical: 0, warning: 0, advisory: 0 }, parts: [{ evaluated: true }] },
      loading: true,
      refresh: vi.fn(),
    });
    mocks.stress.mockReturnValue({
      report: { summary: { warning: 0, advisory: 0 } },
      loading: true,
      refresh: vi.fn(),
    });

    render(
      <ChecksPanel
        buildId={2}
        active
        hasParams={false}
        selectedId={null}
        onSelectPart={() => {}}
        open={
          {
            "checks.goals": true,
            "checks.dfm": true,
            "checks.stress": true,
            "checks.fit": true,
          } as SectionState
        }
        onToggleSection={() => {}}
      />,
    );

    expect(screen.queryByText("All checks pass")).toBeNull();
    expect(screen.queryByText("DFM clear")).toBeNull();
    expect(screen.queryByText("Stress clear")).toBeNull();
    expect(screen.getByText("Checking…")).toBeTruthy();
  });
});
