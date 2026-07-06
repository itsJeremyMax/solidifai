// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup, within } from "@testing-library/react";

import AssemblyTree from "./AssemblyTree";
import type { ModelObject } from "../../lib/artifacts";

afterEach(cleanup);

/** Minimal ModelObject for a path id; satisfies the required fields. */
const obj = (id: string): ModelObject => ({
  id,
  name: id.split("/").pop()!,
  kind: "Part",
  node: id,
  visible: true,
});

const fixture: ModelObject[] = [obj("base"), obj("lid"), obj("hinge/pin"), obj("hinge/knuckle")];

function renderTree(over: Partial<React.ComponentProps<typeof AssemblyTree>> = {}) {
  const props = {
    objects: fixture,
    selectedId: null as string | null,
    hiddenIds: new Set<string>(),
    onSelect: vi.fn(),
    onToggleVisible: vi.fn(),
    materialOverrides: {},
    onSetPartMaterial: vi.fn(),
    ...over,
  };
  render(<AssemblyTree {...props} />);
  return props;
}

describe("AssemblyTree", () => {
  it("renders the hinge group with two children expanded by default", () => {
    renderTree();
    // Group label + its two leaf labels are all present.
    expect(screen.getByText("hinge")).toBeTruthy();
    expect(screen.getByText("pin")).toBeTruthy();
    expect(screen.getByText("knuckle")).toBeTruthy();
    // Flat top-level leaves render too.
    expect(screen.getByText("base")).toBeTruthy();
    expect(screen.getByText("lid")).toBeTruthy();
  });

  it("shows the descendant-leaf count on a group row", () => {
    renderTree();
    expect(screen.getByText("2 parts")).toBeTruthy();
  });

  it("clicking a group row selects the group prefix id", () => {
    const props = renderTree();
    fireEvent.click(screen.getByText("hinge"));
    expect(props.onSelect).toHaveBeenCalledWith("hinge");
  });

  it("clicking a leaf row selects that leaf's full path id", () => {
    const props = renderTree();
    fireEvent.click(screen.getByText("pin"));
    expect(props.onSelect).toHaveBeenCalledWith("hinge/pin");
  });

  it("toggling a group's eye toggles every descendant leaf", () => {
    const props = renderTree();
    fireEvent.click(screen.getByLabelText("Hide hinge"));
    expect(props.onToggleVisible).toHaveBeenCalledWith("hinge/pin");
    expect(props.onToggleVisible).toHaveBeenCalledWith("hinge/knuckle");
    expect(props.onToggleVisible).toHaveBeenCalledTimes(2);
  });

  it("collapsing a group hides its children rows", () => {
    renderTree();
    expect(screen.getByText("pin")).toBeTruthy();
    fireEvent.click(screen.getByLabelText("Collapse hinge"));
    expect(screen.queryByText("pin")).toBeNull();
    // Re-expand restores them.
    fireEvent.click(screen.getByLabelText("Expand hinge"));
    expect(screen.getByText("pin")).toBeTruthy();
  });

  it("a leaf row exposes the same per-part affordances as the flat list", () => {
    renderTree();
    expect(screen.getByLabelText("Material for pin")).toBeTruthy();
    expect(screen.getByLabelText("Hide pin")).toBeTruthy();
  });

  it("does not call onToggleVisible for an already-hidden descendant when hiding a partly-hidden group", () => {
    // pin already hidden; hiding the group should only flip knuckle.
    const props = renderTree({ hiddenIds: new Set(["hinge/pin"]) });
    fireEvent.click(screen.getByLabelText("Hide hinge"));
    expect(props.onToggleVisible).toHaveBeenCalledWith("hinge/knuckle");
    expect(props.onToggleVisible).toHaveBeenCalledTimes(1);
  });

  it("a single flat object renders one leaf row with no group chrome", () => {
    renderTree({ objects: [obj("Bracket")] });
    const row = screen.getByText("Bracket").closest('[role="button"]')!;
    expect(within(row as HTMLElement).queryByLabelText(/Expand|Collapse/)).toBeNull();
  });
});
