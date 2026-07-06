// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, act, cleanup } from "@testing-library/react";
import { createMemoryRouter, RouterProvider, Outlet } from "react-router-dom";

afterEach(cleanup);
import { useEngineLifecycle } from "./useEngineLifecycle";

const open = vi.fn().mockResolvedValue(undefined);
const close = vi.fn().mockResolvedValue(undefined);
vi.mock("../lib/workspaces", () => ({
  openWorkspace: (p: string) => open(p),
  closeWorkspace: () => close(),
}));

// A persistent layout (never unmounts across navigation) — mirrors real AppLayout.
function Layout() {
  useEngineLifecycle();
  return <Outlet />;
}

const enc = encodeURIComponent("/a");
const encB = encodeURIComponent("/b");

function makeRouter(initial: string) {
  return createMemoryRouter(
    [
      {
        element: <Layout />,
        children: [
          { path: "/", element: <div>home</div> },
          {
            path: "/w/:wsPath",
            children: [
              { index: true, element: <div>editor</div> },
              { path: "settings", element: <div>editor-settings</div> },
            ],
          },
        ],
      },
    ],
    { initialEntries: [initial] },
  );
}

beforeEach(() => {
  open.mockClear();
  close.mockClear();
});

describe("useEngineLifecycle", () => {
  it("opens (ensure+focus) the workspace when entering an editor route", () => {
    render(<RouterProvider router={makeRouter(`/w/${enc}`)} />);
    expect(open).toHaveBeenCalledWith("/a");
    expect(close).not.toHaveBeenCalled();
  });

  it("does NOT close on navigation from the editor back to the launcher", async () => {
    const router = makeRouter(`/w/${enc}`);
    render(<RouterProvider router={router} />);
    open.mockClear();
    close.mockClear();
    await act(async () => {
      await router.navigate("/");
    });
    // N live instances: leaving a workspace never tears it down.
    expect(close).not.toHaveBeenCalled();
    expect(open).not.toHaveBeenCalled();
  });

  it("focuses the new workspace without closing the old one when switching", async () => {
    const router = makeRouter(`/w/${enc}`);
    render(<RouterProvider router={router} />);
    open.mockClear();
    close.mockClear();
    await act(async () => {
      await router.navigate(`/w/${encB}`);
    });
    // Open (ensure+focus) the new one; the old one stays live (no close).
    expect(open).toHaveBeenCalledWith("/b");
    expect(close).not.toHaveBeenCalled();
  });

  it("does not re-open or close when moving between nested editor routes", async () => {
    const router = makeRouter(`/w/${enc}`);
    render(<RouterProvider router={router} />);
    open.mockClear();
    close.mockClear();
    await act(async () => {
      await router.navigate(`/w/${enc}/settings`);
    });
    // Same workspace path: no transition, so no open/close churn.
    expect(open).not.toHaveBeenCalled();
    expect(close).not.toHaveBeenCalled();
  });
});
