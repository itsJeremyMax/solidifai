// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LibraryToolbar } from "./LibraryToolbar";

afterEach(cleanup);

const base = {
  query: "",
  onQuery: vi.fn(),
  filter: "all" as const,
  onFilter: vi.fn(),
  view: "grid" as const,
  onView: vi.fn(),
  onNew: vi.fn(),
  counts: { all: 6, archived: 2 },
  tagFilter: null,
  onClearTag: vi.fn(),
};

describe("LibraryToolbar", () => {
  it("typing calls onQuery", async () => {
    const onQuery = vi.fn();
    render(<LibraryToolbar {...base} onQuery={onQuery} />);
    await userEvent.type(screen.getByPlaceholderText(/search workspaces/i), "v");
    expect(onQuery).toHaveBeenCalledWith("v");
  });
  it("clicking Archived calls onFilter", async () => {
    const onFilter = vi.fn();
    render(<LibraryToolbar {...base} onFilter={onFilter} />);
    await userEvent.click(screen.getByRole("button", { name: /archived/i }));
    expect(onFilter).toHaveBeenCalledWith("archived");
  });
  it("clicking list toggles the view", async () => {
    const onView = vi.fn();
    render(<LibraryToolbar {...base} onView={onView} />);
    await userEvent.click(screen.getByRole("button", { name: /list view/i }));
    expect(onView).toHaveBeenCalledWith("list");
  });
  it("New workspace calls onNew", async () => {
    const onNew = vi.fn();
    render(<LibraryToolbar {...base} onNew={onNew} />);
    await userEvent.click(screen.getByRole("button", { name: /new workspace/i }));
    expect(onNew).toHaveBeenCalled();
  });
  it("shows active tag pill and calls onClearTag when X is clicked", async () => {
    const onClearTag = vi.fn();
    render(<LibraryToolbar {...base} tagFilter="prototype" onClearTag={onClearTag} />);
    expect(screen.getByText(/#prototype/)).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: /clear tag filter/i }));
    expect(onClearTag).toHaveBeenCalled();
  });
});
