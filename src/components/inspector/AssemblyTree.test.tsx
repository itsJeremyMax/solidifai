// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup, within } from "@testing-library/react";

import AssemblyTree from "./AssemblyTree";
import type { ModelObject } from "../../lib/artifacts";
import type { JointInfo, OccurrenceFamily } from "../../lib/assemblyMeta";

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

/* ── occurrences + joints (get_assembly_tree metadata) ─────────────────────── */

const instanced: ModelObject[] = [
  obj("wheel/wheel"),
  obj("wheel_2/wheel"),
  obj("wheel_3/wheel"),
  obj("arm/arm"),
];

const wheelFamilies = () =>
  new Map<string, OccurrenceFamily>([
    [
      "wheel",
      {
        primaryId: "wheel",
        displayBase: "wheel",
        memberIds: ["wheel", "wheel_2", "wheel_3"],
        occurrences: [
          { frame: "hub_a", mirror: null, label: "wheel" },
          { frame: "hub_b", mirror: null, label: "wheel@2" },
          { frame: "hub_c", mirror: "yz", label: "wheel@3" },
        ],
        isAssembly: false,
      },
    ],
  ]);

const hingeJoint: JointInfo[] = [
  {
    name: "hinge",
    displayName: "hinge",
    kind: "revolute",
    frame: "pivot",
    axis: [0, 0, 1],
    limits: [0, 120],
    between: ["arm", "post"],
  },
];

describe("AssemblyTree occurrences + joints", () => {
  it("folds an instanced part into one row with a ×N badge", () => {
    renderTree({ objects: instanced, families: wheelFamilies() });
    expect(screen.getByText("×3")).toBeTruthy();
    // The extra placements are not separate rows until expanded.
    expect(screen.queryByText("wheel@2")).toBeNull();
    // wheel_2 / wheel_3 never surface as their own groups.
    expect(screen.queryByText("wheel_2")).toBeNull();
  });

  it("selecting the instanced row selects the primary id (which spans all copies)", () => {
    const props = renderTree({ objects: instanced, families: wheelFamilies() });
    fireEvent.click(screen.getByText("wheel"));
    expect(props.onSelect).toHaveBeenCalledWith("wheel");
  });

  it("expanding shows the frame list with a mirror tag", () => {
    renderTree({ objects: instanced, families: wheelFamilies() });
    fireEvent.click(screen.getByLabelText("Show wheel placements"));
    expect(screen.getByText("wheel@2")).toBeTruthy();
    expect(screen.getByText("wheel@3")).toBeTruthy();
    expect(screen.getByText("at hub_a")).toBeTruthy();
    expect(screen.getByText("mirror yz")).toBeTruthy();
  });

  it("the instanced row's eye toggles every placement's object", () => {
    const props = renderTree({ objects: instanced, families: wheelFamilies() });
    fireEvent.click(screen.getByLabelText("Hide wheel"));
    expect(props.onToggleVisible).toHaveBeenCalledWith("wheel/wheel");
    expect(props.onToggleVisible).toHaveBeenCalledWith("wheel_2/wheel");
    expect(props.onToggleVisible).toHaveBeenCalledWith("wheel_3/wheel");
    expect(props.onToggleVisible).toHaveBeenCalledTimes(3);
  });

  it("renders a read-only joints section", () => {
    renderTree({ objects: instanced, families: wheelFamilies(), joints: hingeJoint });
    expect(screen.getByText("Joints")).toBeTruthy();
    expect(screen.getByText("hinge")).toBeTruthy();
    expect(screen.getByText("revolute")).toBeTruthy();
    expect(screen.getByText(/limits 0 to 120/)).toBeTruthy();
    expect(screen.getByText(/arm ↔ post/)).toBeTruthy();
  });

  it("no joints section when the assembly declares none", () => {
    renderTree({ objects: instanced, families: wheelFamilies() });
    expect(screen.queryByText("Joints")).toBeNull();
  });
});

/* ── instanced sub-assembly: per-placement internals ───────────────────────── */

const rigObjects: ModelObject[] = [obj("rig/blk/body"), obj("rig_2/blk/body")];

const rigFamilies = () =>
  new Map<string, OccurrenceFamily>([
    [
      "rig",
      {
        primaryId: "rig",
        displayBase: "rig",
        memberIds: ["rig", "rig_2"],
        occurrences: [
          { frame: "a", mirror: null, label: "rig" },
          { frame: "b", mirror: "yz", label: "rig@2" },
        ],
        isAssembly: true,
      },
    ],
  ]);

describe("AssemblyTree instanced sub-assembly", () => {
  it("badges the sub-assembly and hides placements until expanded", () => {
    renderTree({ objects: rigObjects, families: rigFamilies() });
    expect(screen.getByText("×2")).toBeTruthy();
    expect(screen.queryByText("rig@2")).toBeNull();
  });

  it("expanding reveals each placement's real internals, not just a frame list", () => {
    renderTree({ objects: rigObjects, families: rigFamilies() });
    fireEvent.click(screen.getByLabelText("Show rig placements"));
    // Each placement is its own expandable group carrying its blk body.
    expect(screen.getByText("rig@2")).toBeTruthy();
    expect(screen.getByText("at b")).toBeTruthy();
    expect(screen.getByText("mirror yz")).toBeTruthy();
    // Each placement contributes its own blk group + body leaf.
    expect(screen.getAllByText("blk").length).toBe(2);
    expect(screen.getAllByText("body").length).toBe(2);
  });

  it("a nested placement leaf selects its own object id", () => {
    const props = renderTree({ objects: rigObjects, families: rigFamilies() });
    fireEvent.click(screen.getByLabelText("Show rig placements"));
    const bodies = screen.getAllByText("body");
    fireEvent.click(bodies[1]); // the second placement's body
    expect(props.onSelect).toHaveBeenCalledWith("rig_2/blk/body");
  });
});
