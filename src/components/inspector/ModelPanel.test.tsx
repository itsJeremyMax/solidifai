// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ModelPanel from "./ModelPanel";
import type { ModelInfo } from "../../lib/artifacts";
import { DEFAULT_OPEN } from "../../state/useInspectorPrefs";

const commit = vi.fn();

vi.mock("../../hooks/useParamCommit", () => ({
  useParamCommit: () => commit,
}));

vi.mock("../../hooks/useAssemblyMeta", () => ({
  useAssemblyMeta: () => ({ families: [], joints: [] }),
}));

function makeModelInfo(params: ModelInfo["params"]): ModelInfo {
  return {
    schema: 2,
    buildId: 7,
    units: "mm",
    build: { ok: true, durationMs: 1, warnings: [] },
    objects: [],
    bbox: { size: [1, 1, 1], min: [0, 0, 0], max: [1, 1, 1] },
    volume: 1,
    centerOfMass: [0, 0, 0],
    mass: { value: 1, material: "PLA", density: 1.24 },
    valid: true,
    manifold: true,
    params,
  };
}

describe("ModelPanel parameter controls", () => {
  afterEach(() => {
    commit.mockReset();
    cleanup();
  });

  it("renders boolean and enum params with editable controls", () => {
    render(
      <ModelPanel
        model={makeModelInfo({
          schema: {
            size: {
              value: 20,
              min: 5,
              max: 100,
              step: 1,
              unit: "mm",
              desc: "Edge length",
            },
            enabled: { type: "boolean", value: true, desc: "Show the full body" },
            mode: {
              type: "enum",
              value: "draft",
              choices: ["draft", "final"],
              desc: "Output mode",
            },
          },
          values: { size: 20, enabled: true, mode: "draft" },
        })}
        active={true}
        onRefresh={async () => {}}
        onBuilding={() => {}}
        open={{ ...DEFAULT_OPEN, "model.explore": true }}
        onToggleSection={() => {}}
        selectedId={null}
        hiddenIds={new Set()}
        onSelect={() => {}}
        onToggleVisible={() => {}}
        onToggleAll={() => {}}
        materialOverrides={{}}
        onSetPartMaterial={() => {}}
      />,
    );

    expect(screen.getByRole("switch", { name: "Enabled" }).getAttribute("aria-checked")).toBe(
      "true",
    );
    expect((screen.getByRole("combobox", { name: "Mode" }) as HTMLSelectElement).value).toBe(
      "draft",
    );
  });

  it("associates enum descriptions with the select via aria-describedby", () => {
    render(
      <ModelPanel
        model={makeModelInfo({
          schema: {
            mode: {
              type: "enum",
              value: "draft",
              choices: ["draft", "final"],
              desc: "Output mode",
            },
          },
          values: { mode: "draft" },
        })}
        active={true}
        onRefresh={async () => {}}
        onBuilding={() => {}}
        open={DEFAULT_OPEN}
        onToggleSection={() => {}}
        selectedId={null}
        hiddenIds={new Set()}
        onSelect={() => {}}
        onToggleVisible={() => {}}
        onToggleAll={() => {}}
        materialOverrides={{}}
        onSetPartMaterial={() => {}}
      />,
    );

    const select = screen.getByRole("combobox", { name: "Mode" });
    const descId = select.getAttribute("aria-describedby");
    expect(descId).toBeTruthy();
    expect(document.getElementById(descId ?? "")?.textContent).toContain("Output mode");
  });

  it("commits boolean and enum edits through the shared param commit path", () => {
    render(
      <ModelPanel
        model={makeModelInfo({
          schema: {
            enabled: { type: "boolean", value: true, desc: "Show the full body" },
            mode: {
              type: "enum",
              value: "draft",
              choices: ["draft", "final"],
              desc: "Output mode",
            },
          },
          values: { enabled: true, mode: "draft" },
        })}
        active={true}
        onRefresh={async () => {}}
        onBuilding={() => {}}
        open={DEFAULT_OPEN}
        onToggleSection={() => {}}
        selectedId={null}
        hiddenIds={new Set()}
        onSelect={() => {}}
        onToggleVisible={() => {}}
        onToggleAll={() => {}}
        materialOverrides={{}}
        onSetPartMaterial={() => {}}
      />,
    );

    fireEvent.click(screen.getByRole("switch", { name: "Enabled" }));
    fireEvent.change(screen.getByRole("combobox", { name: "Mode" }), {
      target: { value: "final" },
    });

    expect(commit).toHaveBeenNthCalledWith(1, "enabled", false, expect.any(Function));
    expect(commit).toHaveBeenNthCalledWith(2, "mode", "final", expect.any(Function));
  });

  it("updates boolean controls optimistically and only reconciles when committed props change", () => {
    const model = makeModelInfo({
      schema: {
        enabled: { type: "boolean", value: true, desc: "Show the full body" },
      },
      values: { enabled: true },
    });
    const { rerender } = render(
      <ModelPanel
        model={model}
        active={true}
        onRefresh={async () => {}}
        onBuilding={() => {}}
        open={DEFAULT_OPEN}
        onToggleSection={() => {}}
        selectedId={null}
        hiddenIds={new Set()}
        onSelect={() => {}}
        onToggleVisible={() => {}}
        onToggleAll={() => {}}
        materialOverrides={{}}
        onSetPartMaterial={() => {}}
      />,
    );

    const toggle = screen.getByRole("switch", { name: "Enabled" });
    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-checked")).toBe("false");

    rerender(
      <ModelPanel
        model={model}
        active={true}
        onRefresh={async () => {}}
        onBuilding={() => {}}
        open={DEFAULT_OPEN}
        onToggleSection={() => {}}
        selectedId={null}
        hiddenIds={new Set()}
        onSelect={() => {}}
        onToggleVisible={() => {}}
        onToggleAll={() => {}}
        materialOverrides={{}}
        onSetPartMaterial={() => {}}
      />,
    );
    expect(screen.getByRole("switch", { name: "Enabled" }).getAttribute("aria-checked")).toBe(
      "false",
    );

    rerender(
      <ModelPanel
        model={{ ...model, buildId: 8, params: { ...model.params, values: { enabled: false } } }}
        active={true}
        onRefresh={async () => {}}
        onBuilding={() => {}}
        open={DEFAULT_OPEN}
        onToggleSection={() => {}}
        selectedId={null}
        hiddenIds={new Set()}
        onSelect={() => {}}
        onToggleVisible={() => {}}
        onToggleAll={() => {}}
        materialOverrides={{}}
        onSetPartMaterial={() => {}}
      />,
    );
    expect(screen.getByRole("switch", { name: "Enabled" }).getAttribute("aria-checked")).toBe(
      "false",
    );
  });

  it("reverts an optimistic boolean toggle when the real commit callback reports failure", async () => {
    render(
      <ModelPanel
        model={makeModelInfo({
          schema: {
            enabled: { type: "boolean", value: true, desc: "Show the full body" },
          },
          values: { enabled: true },
        })}
        active={true}
        onRefresh={async () => {}}
        onBuilding={() => {}}
        open={DEFAULT_OPEN}
        onToggleSection={() => {}}
        selectedId={null}
        hiddenIds={new Set()}
        onSelect={() => {}}
        onToggleVisible={() => {}}
        onToggleAll={() => {}}
        materialOverrides={{}}
        onSetPartMaterial={() => {}}
      />,
    );

    fireEvent.click(screen.getByRole("switch", { name: "Enabled" }));
    expect(screen.getByRole("switch", { name: "Enabled" }).getAttribute("aria-checked")).toBe(
      "false",
    );

    const onError = commit.mock.calls[0]?.[2] as ((error: unknown) => void) | undefined;
    expect(onError).toBeTypeOf("function");
    onError?.(new Error("engine not ready"));

    await waitFor(() => {
      expect(screen.getByRole("switch", { name: "Enabled" }).getAttribute("aria-checked")).toBe(
        "true",
      );
    });
  });

  it("updates enum controls optimistically, ignores stale failures, and reconciles on committed props", async () => {
    const model = makeModelInfo({
      schema: {
        mode: {
          type: "enum",
          value: "draft",
          choices: ["draft", "review", "final"],
          desc: "Output mode",
        },
      },
      values: { mode: "draft" },
    });
    const { rerender } = render(
      <ModelPanel
        model={model}
        active={true}
        onRefresh={async () => {}}
        onBuilding={() => {}}
        open={DEFAULT_OPEN}
        onToggleSection={() => {}}
        selectedId={null}
        hiddenIds={new Set()}
        onSelect={() => {}}
        onToggleVisible={() => {}}
        onToggleAll={() => {}}
        materialOverrides={{}}
        onSetPartMaterial={() => {}}
      />,
    );

    fireEvent.change(screen.getByRole("combobox", { name: "Mode" }), {
      target: { value: "final" },
    });
    expect((screen.getByRole("combobox", { name: "Mode" }) as HTMLSelectElement).value).toBe(
      "final",
    );

    fireEvent.change(screen.getByRole("combobox", { name: "Mode" }), {
      target: { value: "review" },
    });
    expect((screen.getByRole("combobox", { name: "Mode" }) as HTMLSelectElement).value).toBe(
      "review",
    );

    const firstOnError = commit.mock.calls[0]?.[2] as ((error: unknown) => void) | undefined;
    expect(firstOnError).toBeTypeOf("function");
    firstOnError?.(new Error("stale failure"));
    await Promise.resolve();
    expect((screen.getByRole("combobox", { name: "Mode" }) as HTMLSelectElement).value).toBe(
      "review",
    );

    rerender(
      <ModelPanel
        model={model}
        active={true}
        onRefresh={async () => {}}
        onBuilding={() => {}}
        open={DEFAULT_OPEN}
        onToggleSection={() => {}}
        selectedId={null}
        hiddenIds={new Set()}
        onSelect={() => {}}
        onToggleVisible={() => {}}
        onToggleAll={() => {}}
        materialOverrides={{}}
        onSetPartMaterial={() => {}}
      />,
    );
    expect((screen.getByRole("combobox", { name: "Mode" }) as HTMLSelectElement).value).toBe(
      "review",
    );

    rerender(
      <ModelPanel
        model={{ ...model, buildId: 8, params: { ...model.params, values: { mode: "review" } } }}
        active={true}
        onRefresh={async () => {}}
        onBuilding={() => {}}
        open={DEFAULT_OPEN}
        onToggleSection={() => {}}
        selectedId={null}
        hiddenIds={new Set()}
        onSelect={() => {}}
        onToggleVisible={() => {}}
        onToggleAll={() => {}}
        materialOverrides={{}}
        onSetPartMaterial={() => {}}
      />,
    );
    expect((screen.getByRole("combobox", { name: "Mode" }) as HTMLSelectElement).value).toBe(
      "review",
    );
  });

  it("ignores stale committed props while a newer local enum edit is still awaiting acknowledgement", () => {
    const model = makeModelInfo({
      schema: {
        mode: {
          type: "enum",
          value: "draft",
          choices: ["draft", "review", "final"],
          desc: "Output mode",
        },
      },
      values: { mode: "draft" },
    });
    const { rerender } = render(
      <ModelPanel
        model={model}
        active={true}
        onRefresh={async () => {}}
        onBuilding={() => {}}
        open={DEFAULT_OPEN}
        onToggleSection={() => {}}
        selectedId={null}
        hiddenIds={new Set()}
        onSelect={() => {}}
        onToggleVisible={() => {}}
        onToggleAll={() => {}}
        materialOverrides={{}}
        onSetPartMaterial={() => {}}
      />,
    );

    fireEvent.change(screen.getByRole("combobox", { name: "Mode" }), {
      target: { value: "final" },
    });
    fireEvent.change(screen.getByRole("combobox", { name: "Mode" }), {
      target: { value: "draft" },
    });
    expect((screen.getByRole("combobox", { name: "Mode" }) as HTMLSelectElement).value).toBe(
      "draft",
    );

    rerender(
      <ModelPanel
        model={{ ...model, buildId: 8, params: { ...model.params, values: { mode: "final" } } }}
        active={true}
        onRefresh={async () => {}}
        onBuilding={() => {}}
        open={DEFAULT_OPEN}
        onToggleSection={() => {}}
        selectedId={null}
        hiddenIds={new Set()}
        onSelect={() => {}}
        onToggleVisible={() => {}}
        onToggleAll={() => {}}
        materialOverrides={{}}
        onSetPartMaterial={() => {}}
      />,
    );
    expect((screen.getByRole("combobox", { name: "Mode" }) as HTMLSelectElement).value).toBe(
      "draft",
    );

    rerender(
      <ModelPanel
        model={model}
        active={true}
        onRefresh={async () => {}}
        onBuilding={() => {}}
        open={DEFAULT_OPEN}
        onToggleSection={() => {}}
        selectedId={null}
        hiddenIds={new Set()}
        onSelect={() => {}}
        onToggleVisible={() => {}}
        onToggleAll={() => {}}
        materialOverrides={{}}
        onSetPartMaterial={() => {}}
      />,
    );
    expect((screen.getByRole("combobox", { name: "Mode" }) as HTMLSelectElement).value).toBe(
      "draft",
    );

    rerender(
      <ModelPanel
        model={{ ...model, buildId: 9, params: { ...model.params, values: { mode: "draft" } } }}
        active={true}
        onRefresh={async () => {}}
        onBuilding={() => {}}
        open={DEFAULT_OPEN}
        onToggleSection={() => {}}
        selectedId={null}
        hiddenIds={new Set()}
        onSelect={() => {}}
        onToggleVisible={() => {}}
        onToggleAll={() => {}}
        materialOverrides={{}}
        onSetPartMaterial={() => {}}
      />,
    );
    expect((screen.getByRole("combobox", { name: "Mode" }) as HTMLSelectElement).value).toBe(
      "draft",
    );
  });
});
