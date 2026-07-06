// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";

import WorkspaceSwitcher from "./WorkspaceSwitcher";

afterEach(cleanup);

describe("WorkspaceSwitcher", () => {
  it("renders a pill per open workspace and focuses on click", () => {
    const onFocus = vi.fn();
    render(
      <WorkspaceSwitcher
        openPaths={["/ws/a", "/ws/b"]}
        focusedPath="/ws/a"
        names={{ "/ws/a": "Alpha", "/ws/b": "Beta" }}
        statuses={{ "/ws/a": "ready", "/ws/b": "provisioning" }}
        onFocus={onFocus}
        onClose={vi.fn()}
        onAdd={vi.fn()}
      />,
    );
    expect(screen.getByText("Alpha")).toBeTruthy();
    fireEvent.click(screen.getByText("Beta"));
    expect(onFocus).toHaveBeenCalledWith("/ws/b");
  });

  it("marks the focused pill with aria-pressed", () => {
    render(
      <WorkspaceSwitcher
        openPaths={["/ws/a", "/ws/b"]}
        focusedPath="/ws/b"
        names={{ "/ws/a": "Alpha", "/ws/b": "Beta" }}
        statuses={{}}
        onFocus={vi.fn()}
        onClose={vi.fn()}
        onAdd={vi.fn()}
      />,
    );
    expect(screen.getByText("Beta").closest("button")?.getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByText("Alpha").closest("button")?.getAttribute("aria-pressed")).toBe("false");
  });

  it("close affordance fires onClose", () => {
    const onClose = vi.fn();
    render(
      <WorkspaceSwitcher
        openPaths={["/ws/a"]}
        focusedPath="/ws/a"
        names={{ "/ws/a": "Alpha" }}
        statuses={{}}
        onFocus={vi.fn()}
        onClose={onClose}
        onAdd={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByLabelText("Close Alpha"));
    expect(onClose).toHaveBeenCalledWith("/ws/a");
  });

  it("does not focus the tab when the close affordance is clicked", () => {
    const onFocus = vi.fn();
    const onClose = vi.fn();
    render(
      <WorkspaceSwitcher
        openPaths={["/ws/a"]}
        focusedPath="/ws/a"
        names={{ "/ws/a": "Alpha" }}
        statuses={{}}
        onFocus={onFocus}
        onClose={onClose}
        onAdd={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByLabelText("Close Alpha"));
    expect(onClose).toHaveBeenCalledWith("/ws/a");
    expect(onFocus).not.toHaveBeenCalled();
  });

  it("middle-click on a pill closes it", () => {
    const onClose = vi.fn();
    render(
      <WorkspaceSwitcher
        openPaths={["/ws/a"]}
        focusedPath="/ws/a"
        names={{ "/ws/a": "Alpha" }}
        statuses={{}}
        onFocus={vi.fn()}
        onClose={onClose}
        onAdd={vi.fn()}
      />,
    );
    fireEvent.mouseDown(screen.getByText("Alpha").closest("button")!, { button: 1 });
    expect(onClose).toHaveBeenCalledWith("/ws/a");
  });

  it("collapses past five tabs into a +N overflow that lists the rest", () => {
    const onFocus = vi.fn();
    const paths = ["/ws/1", "/ws/2", "/ws/3", "/ws/4", "/ws/5", "/ws/6", "/ws/7"];
    const names = Object.fromEntries(paths.map((p, i) => [p, `W${i + 1}`]));
    render(
      <WorkspaceSwitcher
        openPaths={paths}
        focusedPath="/ws/1"
        names={names}
        statuses={{ "/ws/6": "provisioning" }}
        onFocus={onFocus}
        onClose={vi.fn()}
        onAdd={vi.fn()}
      />,
    );
    // Five pills visible; the 6th/7th are hidden behind the chip.
    expect(screen.queryByText("W6")).toBeNull();
    const chip = screen.getByText("+2");
    fireEvent.click(chip);
    // Now the collapsed tabs are listed; clicking one focuses it.
    fireEvent.click(screen.getByText("W7"));
    expect(onFocus).toHaveBeenCalledWith("/ws/7");
  });

  it("fires onAdd from the add button", () => {
    const onAdd = vi.fn();
    render(
      <WorkspaceSwitcher
        openPaths={["/ws/a"]}
        focusedPath="/ws/a"
        names={{ "/ws/a": "Alpha" }}
        statuses={{}}
        onFocus={vi.fn()}
        onClose={vi.fn()}
        onAdd={onAdd}
      />,
    );
    fireEvent.click(screen.getByLabelText("Open a workspace"));
    expect(onAdd).toHaveBeenCalled();
  });
});
