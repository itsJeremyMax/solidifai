// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";

import InspectorTabs from "./InspectorTabs";
import { INSPECTOR_TABS } from "./tabs";

afterEach(cleanup);

describe("InspectorTabs", () => {
  it("renders every tab label (no icon-only tabs to hover-guess)", () => {
    render(<InspectorTabs active="model" onSelect={() => {}} />);
    for (const t of INSPECTOR_TABS) {
      expect(screen.getByRole("tab", { name: new RegExp(t.label) })).toBeTruthy();
    }
  });

  it("marks only the active tab selected and selects on click", () => {
    const onSelect = vi.fn();
    render(<InspectorTabs active="model" onSelect={onSelect} />);
    expect(screen.getByRole("tab", { name: /Model/ }).getAttribute("aria-selected")).toBe("true");
    expect(screen.getByRole("tab", { name: /Make/ }).getAttribute("aria-selected")).toBe("false");
    fireEvent.click(screen.getByRole("tab", { name: /Checks/ }));
    expect(onSelect).toHaveBeenCalledWith("checks");
  });

  it("moves the selection with arrow keys, wrapping at the ends", () => {
    const onSelect = vi.fn();
    render(<InspectorTabs active="model" onSelect={onSelect} />);
    const tablist = screen.getByRole("tablist");
    fireEvent.keyDown(tablist, { key: "ArrowRight" });
    expect(onSelect).toHaveBeenLastCalledWith("checks");
    fireEvent.keyDown(tablist, { key: "ArrowLeft" });
    expect(onSelect).toHaveBeenLastCalledWith("make"); // wraps left from the first tab
    fireEvent.keyDown(tablist, { key: "End" });
    expect(onSelect).toHaveBeenLastCalledWith("make");
    fireEvent.keyDown(tablist, { key: "Home" });
    expect(onSelect).toHaveBeenLastCalledWith("model");
  });

  it("shows a badge dot only on an inactive badged tab", () => {
    const { rerender } = render(
      <InspectorTabs active="model" onSelect={() => {}} badges={{ activity: true }} />,
    );
    const activity = () => screen.getByRole("tab", { name: /Activity/ });
    expect(activity().querySelector("span")).toBeTruthy();
    rerender(<InspectorTabs active="activity" onSelect={() => {}} badges={{ activity: true }} />);
    expect(activity().querySelector("span")).toBeNull();
  });
});
