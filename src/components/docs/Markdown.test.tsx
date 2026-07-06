// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

const openUrl = vi.fn();
vi.mock("@tauri-apps/plugin-opener", () => ({ openUrl: (u: string) => openUrl(u) }));

import { Markdown } from "./Markdown";
import { slugifyHeading } from "../../lib/docs";

afterEach(() => {
  cleanup();
  openUrl.mockReset();
});

function mount(md: string) {
  return render(
    <MemoryRouter>
      <Markdown source={md} />
    </MemoryRouter>,
  );
}

describe("Markdown", () => {
  it("gives headings stable ids for the rail and deep links", () => {
    mount("## The viewport\n\ntext");
    expect(document.getElementById(slugifyHeading("The viewport"))).toBeTruthy();
  });

  it("opens external links in the system browser, not in-app", () => {
    mount("[site](https://example.com)");
    fireEvent.click(screen.getByText("site"));
    expect(openUrl).toHaveBeenCalledWith("https://example.com");
  });

  it("renders a NOTE blockquote as an alert with a label", () => {
    mount("> [!NOTE]\n> Heads up.");
    expect(screen.getByText("Note")).toBeTruthy();
    expect(screen.getByText("Heads up.")).toBeTruthy();
  });

  it("renders a WARNING blockquote as an alert", () => {
    mount("> [!WARNING]\n> Careful here.");
    expect(screen.getByText("Warning")).toBeTruthy();
    expect(screen.getByText("Careful here.")).toBeTruthy();
  });

  it("renders a GFM table", () => {
    mount("| A | B |\n| - | - |\n| 1 | 2 |");
    expect(screen.getByRole("table")).toBeTruthy();
    expect(screen.getByText("A")).toBeTruthy();
  });
});
